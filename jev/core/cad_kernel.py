"""
Núcleo geométrico CAD paramétrico de JEV (CAD Kernel).

Motor de modelado 3D por sólidos para el Viewport en vivo y el pipeline de
fabricación digital. Construye geometría real (no aproximaciones por primitivas)
con dos backends:

1. manifold3d (CSG robusto, garantía de variedad): extrusión de perfiles,
   revolución de sólidos, unión/diferencia/intersección de operaciones booleanas.
   Es el backend por defecto y el responsable de taladros, vaciados y chaflanes.
2. trimesh: validación de estanqueidad, reparación y exportación a
   STL / GLB / GLTF / OBJ.
3. Fallback nativo en NumPy puro para las piezas que no requieren booleanas
   (engranajes, bridas, arandelas, resortes y codos), de modo que el motor siga
   funcionando aunque manifold3d no esté instalado.

Todos los sólidos se generan en milímetros y centrados en el origen (Z = eje
axial) salvo indicación contraria.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

try:  # Backend CSG principal
    import manifold3d as m3d
    HAS_MANIFOLD = True
except Exception:  # pragma: no cover - entorno sin manifold3d
    m3d = None
    HAS_MANIFOLD = False

try:  # Validación y exportación
    import trimesh
    HAS_TRIMESH = True
except Exception:  # pragma: no cover - entorno sin trimesh
    trimesh = None
    HAS_TRIMESH = False


TAU = 2.0 * math.pi


# ---------------------------------------------------------------------------
# MODELO DE MALLA
# ---------------------------------------------------------------------------
@dataclass
class MeshData:
    """Malla triangular devuelta por el kernel."""

    vertices: np.ndarray
    faces: np.ndarray
    name: str = "part"

    def __post_init__(self) -> None:
        self.vertices = np.asarray(self.vertices, dtype=np.float64).reshape(-1, 3)
        self.faces = np.asarray(self.faces, dtype=np.int64).reshape(-1, 3)
        if len(self.faces) and (self.faces.max() >= len(self.vertices) or self.faces.min() < 0):
            raise ValueError("Índices de cara fuera de rango en la malla generada.")

    # -- Métricas ---------------------------------------------------------
    @property
    def vertex_count(self) -> int:
        return int(len(self.vertices))

    @property
    def face_count(self) -> int:
        return int(len(self.faces))

    @property
    def bounds(self) -> Tuple[np.ndarray, np.ndarray]:
        if not len(self.vertices):
            return np.zeros(3), np.zeros(3)
        return self.vertices.min(axis=0), self.vertices.max(axis=0)

    @property
    def extent(self) -> np.ndarray:
        lo, hi = self.bounds
        return hi - lo

    @property
    def center(self) -> np.ndarray:
        lo, hi = self.bounds
        return (lo + hi) / 2.0

    def volume(self) -> float:
        """Volumen firmado por divergencia sobre tetraedros (mm3)."""
        if not len(self.faces):
            return 0.0
        v0 = self.vertices[self.faces[:, 0]]
        v1 = self.vertices[self.faces[:, 1]]
        v2 = self.vertices[self.faces[:, 2]]
        return float(abs(np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() / 6.0))

    def is_watertight(self) -> Optional[bool]:
        """Comprueba estanqueidad con trimesh si está disponible."""
        if not HAS_TRIMESH:
            return None
        try:
            return bool(self.to_trimesh().is_watertight)
        except Exception:
            return None

    def to_trimesh(self):
        if not HAS_TRIMESH:
            raise RuntimeError("trimesh no está instalado.")
        return trimesh.Trimesh(vertices=self.vertices, faces=self.faces, process=False)

    # -- Transformaciones -------------------------------------------------
    def translate(self, offset: Sequence[float]) -> "MeshData":
        return MeshData(self.vertices + np.asarray(offset, dtype=float), self.faces.copy(), self.name)

    def rotate_z(self, degrees: float) -> "MeshData":
        a = math.radians(float(degrees))
        c, s = math.cos(a), math.sin(a)
        rot = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
        return MeshData(self.vertices @ rot.T, self.faces.copy(), self.name)

    def merged_with(self, other: "MeshData") -> "MeshData":
        offset = len(self.vertices)
        verts = np.vstack([self.vertices, other.vertices])
        faces = np.vstack([self.faces, other.faces + offset])
        return MeshData(verts, faces, self.name)

    @classmethod
    def merge(cls, meshes: Iterable["MeshData"], name: str = "assembly") -> "MeshData":
        meshes = [m for m in meshes if m is not None and len(m.vertices)]
        if not meshes:
            raise ValueError("No hay mallas para fusionar.")
        verts: List[np.ndarray] = []
        faces: List[np.ndarray] = []
        offset = 0
        for mesh in meshes:
            verts.append(mesh.vertices)
            faces.append(mesh.faces + offset)
            offset += len(mesh.vertices)
        return cls(np.vstack(verts), np.vstack(faces), name)


# ---------------------------------------------------------------------------
# HELPERS NUMÉRICOS Y CONTORNOS 2D
# ---------------------------------------------------------------------------
def circle_contour(radius: float, segments: int = 64, phase: float = 0.0) -> np.ndarray:
    """Contorno circular CCW de segments vértices (sin duplicar el primero)."""
    segments = max(8, int(segments))
    angles = np.linspace(0.0, TAU, segments, endpoint=False) + phase
    return np.column_stack([np.cos(angles) * radius, np.sin(angles) * radius])


def hex_contour(across_flats: float) -> np.ndarray:
    """Contorno de tuerca hexagonal CCW dado el entrecaras."""
    r = (across_flats / 2.0) / math.cos(math.pi / 6.0)
    angles = np.linspace(0.0, TAU, 6, endpoint=False) + math.pi / 6.0
    return np.column_stack([np.cos(angles) * r, np.sin(angles) * r])


def rounded_rect_contour(width: float, depth: float, radius: float, corner_steps: int = 8) -> np.ndarray:
    """Contorno de rectángulo redondeado centrado en el origen."""
    hw, hd = width / 2.0, depth / 2.0
    radius = max(0.0, min(radius, min(hw, hd) - 1e-6))
    if radius <= 1e-9:
        return np.array([[-hw, -hd], [hw, -hd], [hw, hd], [-hw, hd]], dtype=float)
    pts: List[Tuple[float, float]] = []
    centers = [
        (hw - radius, -hd + radius, -math.pi / 2.0, 0.0),
        (hw - radius, hd - radius, 0.0, math.pi / 2.0),
        (-hw + radius, hd - radius, math.pi / 2.0, math.pi),
        (-hw + radius, -hd + radius, math.pi, 1.5 * math.pi),
    ]
    for cx, cy, a0, a1 in centers:
        for t in np.linspace(a0, a1, max(2, corner_steps), endpoint=False):
            pts.append((cx + radius * math.cos(t), cy + radius * math.sin(t)))
    return np.asarray(pts, dtype=float)


def gear_contour(
    teeth: int,
    pitch_radius: float,
    tooth_height: float,
    tooth_width_ratio: float = 0.46,
    flank_points: int = 4,
) -> np.ndarray:
    """
    Perfil 2D de engranaje recto (dientes trapezoidales) cerrado y CCW.

    Cada diente se compone de: flanco de subida, cresta, flanco de bajada y el
    hueco de raíz hasta el diente siguiente. El ángulo crece de forma monótona,
    de modo que el contorno es simple y no se auto-intersecta (lo que produciría
    agujeros espurios al rellenar con la regla even-odd).
    """
    teeth = max(4, int(teeth))
    pitch = TAU / teeth
    r_root = max(1e-3, pitch_radius - tooth_height / 2.0)
    r_tip = pitch_radius + tooth_height / 2.0

    # Semiancho angular del diente en la raíz y en la cresta.
    ratio = max(0.2, min(0.8, float(tooth_width_ratio)))
    # Diente: raíz ~0.48*pitch de ancho, cresta ~0.34*pitch, hueco ~0.52*pitch.
    half_root = pitch * ratio * 0.52
    half_tip = pitch * ratio * 0.37
    half_root = max(half_root, half_tip * 1.18)
    flank_points = max(2, int(flank_points))

    pts: List[Tuple[float, float]] = []
    for i in range(teeth):
        center = i * pitch

        # Flanco de subida: raíz -> cresta
        for t in np.linspace(0.0, 1.0, flank_points, endpoint=False):
            a = center - half_root + t * (half_root - half_tip)
            r = r_root + (r_tip - r_root) * t
            pts.append((r * math.cos(a), r * math.sin(a)))

        # Cresta (arco en el radio exterior)
        for t in np.linspace(0.0, 1.0, flank_points, endpoint=False):
            a = center - half_tip + t * (2.0 * half_tip)
            pts.append((r_tip * math.cos(a), r_tip * math.sin(a)))

        # Flanco de bajada: cresta -> raíz
        for t in np.linspace(0.0, 1.0, flank_points, endpoint=False):
            a = center + half_tip + t * (half_root - half_tip)
            r = r_tip - (r_tip - r_root) * t
            pts.append((r * math.cos(a), r * math.sin(a)))

        # Hueco de raíz hasta el inicio del diente siguiente
        gap_start = center + half_root
        gap_end = center + pitch - half_root
        for t in np.linspace(0.0, 1.0, flank_points, endpoint=False):
            a = gap_start + t * (gap_end - gap_start)
            pts.append((r_root * math.cos(a), r_root * math.sin(a)))

    return np.asarray(pts, dtype=float)


def rack_contour(
    teeth: int,
    module: float,
    height: float,
    tooth_height: Optional[float] = None,
    flank_points: int = 3,
) -> np.ndarray:
    """Perfil 2D de cremallera (dientes hacia +Y) con base plana en y=0."""
    teeth = max(2, int(teeth))
    pitch = max(0.2, float(module))
    tooth_height = float(tooth_height if tooth_height is not None else pitch * 1.25)
    total = teeth * pitch
    half_tip = pitch * 0.23
    pts: List[Tuple[float, float]] = [(-total / 2.0, 0.0), (total / 2.0, 0.0)]
    y_tip = height + tooth_height
    for i in range(teeth - 1, -1, -1):
        x0 = -total / 2.0 + i * pitch
        xc = x0 + pitch / 2.0
        pts.append((x0 + pitch, height))
        pts.append((xc + half_tip, y_tip))
        pts.append((xc - half_tip, y_tip))
        pts.append((x0, height))
    return np.asarray(pts, dtype=float)


# ---------------------------------------------------------------------------
# CONVERSIÓN MANIFOLD <-> MALLA
# ---------------------------------------------------------------------------
def _require_manifold(feature: str) -> None:
    if not HAS_MANIFOLD:
        raise RuntimeError(
            "La operación '" + feature + "' requiere manifold3d. Instálalo con: "
            r".\.venv\Scripts\python.exe -m pip install manifold3d"
        )


def solid_to_mesh(solid, name: str = "part") -> MeshData:
    """Convierte un manifold3d.Manifold en MeshData."""
    mesh = solid.to_mesh()
    verts = np.asarray(mesh.vert_properties, dtype=np.float64)
    if verts.shape[1] > 3:
        verts = verts[:, :3]
    faces = np.asarray(mesh.tri_verts, dtype=np.int64)
    return MeshData(verts, faces, name)


def mesh_to_solid(mesh: MeshData):
    _require_manifold("conversión a sólido")
    return m3d.Manifold(
        m3d.Mesh(
            np.asarray(mesh.vertices, dtype=np.float32),
            np.asarray(mesh.faces, dtype=np.uint32),
        )
    )


# ---------------------------------------------------------------------------
# PRIMITIVAS (MANIFOLD)
# ---------------------------------------------------------------------------
def box(w: float, d: float, h: float, center: bool = True):
    _require_manifold("box")
    solid = m3d.Manifold.cube((float(w), float(d), float(h)), True)
    return solid if center else solid.translate((0, 0, h / 2.0))


def cylinder(radius: float, height: float, segments: int = 64, center: bool = True,
             radius_top: Optional[float] = None):
    _require_manifold("cylinder")
    r_top = float(radius if radius_top is None else radius_top)
    return m3d.Manifold.cylinder(float(height), float(radius), r_top, max(8, int(segments)), bool(center))


def sphere(radius: float, segments: int = 48):
    _require_manifold("sphere")
    return m3d.Manifold.sphere(float(radius), max(12, int(segments)))


def extrude(contours: Sequence[np.ndarray], height: float, twist_deg: float = 0.0,
            divisions: int = 0, fillrule_even_odd: bool = True):
    _require_manifold("extrude")
    rule = m3d.FillRule.EvenOdd if fillrule_even_odd else m3d.FillRule.Positive
    cs = m3d.CrossSection([np.asarray(c, dtype=np.float64) for c in contours], rule)
    return m3d.Manifold.extrude(cs, float(height), int(divisions), float(twist_deg))


def revolve(profile: np.ndarray, segments: int = 96, degrees: float = 360.0):
    """Revoluciona un perfil (x=radio, y=altura) alrededor del eje Z."""
    _require_manifold("revolve")
    cs = m3d.CrossSection([np.asarray(profile, dtype=np.float64)], m3d.FillRule.Positive)
    return m3d.Manifold.revolve(cs, max(8, int(segments)), float(degrees))


# ---------------------------------------------------------------------------
# TUBOS BARRIDOS NATIVOS (resortes y codos)
# ---------------------------------------------------------------------------
def _normalize(vec: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(vec)
    return vec / n if n > 1e-12 else np.array([0.0, 0.0, 1.0])


def _rotation_between(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Matriz de rotación que lleva el vector unitario a al vector unitario b."""
    a, b = _normalize(a), _normalize(b)
    v = np.cross(a, b)
    c = float(np.clip(np.dot(a, b), -1.0, 1.0))
    if np.linalg.norm(v) < 1e-12:
        if c > 0:
            return np.eye(3)
        axis = _normalize(np.cross(a, np.array([1.0, 0.0, 0.0])))
        if np.linalg.norm(axis) < 1e-6:
            axis = _normalize(np.cross(a, np.array([0.0, 1.0, 0.0])))
        return np.eye(3) + 2.0 * (np.outer(axis, axis) - np.eye(3))
    vx = np.array([[0.0, -v[2], v[1]], [v[2], 0.0, -v[0]], [-v[1], v[0], 0.0]])
    return np.eye(3) + vx + vx @ vx * (1.0 / (1.0 + c))


def sweep_tube(path: np.ndarray, radius: float, segments: int = 24,
               closed: bool = False, cap: bool = True) -> MeshData:
    """Barre una sección circular a lo largo de una polilínea 3D con tapas."""
    path = np.asarray(path, dtype=float).reshape(-1, 3)
    if len(path) < 2:
        raise ValueError("La trayectoria del tubo necesita al menos 2 puntos.")
    segments = max(6, int(segments))

    tangents = np.zeros_like(path)
    for i in range(len(path)):
        if i == 0:
            tangents[i] = path[1] - path[0]
        elif i == len(path) - 1:
            tangents[i] = path[-1] - path[-2]
        else:
            tangents[i] = path[i + 1] - path[i - 1]
        tangents[i] = _normalize(tangents[i])

    ref = np.array([0.0, 0.0, 1.0])
    if abs(np.dot(ref, tangents[0])) > 0.95:
        ref = np.array([1.0, 0.0, 0.0])
    normal = _normalize(np.cross(tangents[0], ref))
    binormal = _normalize(np.cross(tangents[0], normal))

    frames: List[Tuple[np.ndarray, np.ndarray]] = [(normal, binormal)]
    for i in range(1, len(path)):
        rot = _rotation_between(tangents[i - 1], tangents[i])
        normal = rot @ normal
        binormal = rot @ binormal
        normal = _normalize(normal - tangents[i] * float(np.dot(normal, tangents[i])))
        binormal = _normalize(np.cross(tangents[i], normal))
        frames.append((normal, binormal))

    angles = np.linspace(0.0, TAU, segments, endpoint=False)
    cos_a, sin_a = np.cos(angles), np.sin(angles)

    vertices: List[List[float]] = []
    for center, (n_vec, b_vec) in zip(path, frames):
        ring = center + radius * (np.outer(cos_a, n_vec) + np.outer(sin_a, b_vec))
        vertices.extend(ring.tolist())

    faces: List[Tuple[int, int, int]] = []
    ring_count = len(path)
    loop = ring_count if closed else ring_count - 1
    for i in range(loop):
        a = i * segments
        b = ((i + 1) % ring_count) * segments
        for j in range(segments):
            nj = (j + 1) % segments
            faces.append((a + j, b + j, a + nj))
            faces.append((a + nj, b + j, b + nj))

    if cap and not closed:
        start_center = len(vertices)
        vertices.append(path[0].tolist())
        end_center = len(vertices)
        vertices.append(path[-1].tolist())
        base = (ring_count - 1) * segments
        for j in range(segments):
            nj = (j + 1) % segments
            faces.append((start_center, j, nj))
            faces.append((end_center, base + nj, base + j))

    return MeshData(np.asarray(vertices, dtype=float), np.asarray(faces, dtype=np.int64))


# ---------------------------------------------------------------------------
# PIEZAS PARAMÉTRICAS
# ---------------------------------------------------------------------------
def _quality_segments(quality: str) -> float:
    return {"low": 0.55, "medium": 1.0, "high": 1.7}.get(str(quality).lower(), 1.0)


def _segments(base: int, quality: str) -> int:
    return max(8, int(round(base * _quality_segments(quality))))


def _hole_cutter(count: int, circle_radius: float, hole_radius: float,
                 height: float, quality: str = "medium"):
    """Manifold con count cilindros distribuidos en un círculo (para restar)."""
    _require_manifold("_hole_cutter")
    segments = _segments(32, quality)
    cutter = None
    for i in range(max(1, int(count))):
        ang = i * TAU / max(1, int(count))
        hole = cylinder(hole_radius, height, segments).translate(
            (circle_radius * math.cos(ang), circle_radius * math.sin(ang), 0.0)
        )
        cutter = hole if cutter is None else cutter + hole
    return cutter


def build_spur_gear(params: Dict[str, Any], name: str = "SpurGear") -> MeshData:
    teeth = int(params.get("teeth", 18))
    pitch_radius = float(params.get("pitch_radius", 12.0))
    thickness = float(params.get("thickness", 4.0))
    bore_radius = float(params.get("bore_radius", max(0.5, pitch_radius * 0.28)))
    tooth_height = float(params.get("tooth_height", max(1.5, pitch_radius * 0.12)))
    quality = params.get("quality", "medium")
    lightening_holes = int(params.get("lightening_holes", 0))
    hole_radius = float(params.get("hole_radius", max(0.4, (pitch_radius - bore_radius) * 0.22)))
    hole_circle = float(params.get("hole_circle_radius", (pitch_radius + bore_radius) / 2.0))
    hub_radius = float(params.get("hub_radius", 0.0))
    hub_height = float(params.get("hub_height", 0.0))

    if pitch_radius <= bore_radius * 1.05:
        raise ValueError(
            "pitch_radius debe ser mayor que bore_radius "
            f"(recibido pitch_radius={pitch_radius}, bore_radius={bore_radius})."
        )

    # Mantener los aligeramientos dentro del material disponible
    if lightening_holes > 0:
        r_min = bore_radius + hole_radius * 1.3
        r_max = max(r_min, pitch_radius - tooth_height / 2.0 - hole_radius * 1.3)
        hole_circle = float(min(max(hole_circle, r_min), r_max))

    if HAS_MANIFOLD:
        tooth_profile = gear_contour(teeth, pitch_radius, tooth_height)
        bore_profile = circle_contour(bore_radius, _segments(64, quality))
        solid = extrude([tooth_profile, bore_profile], thickness).translate((0, 0, -thickness / 2.0))
        if hub_radius > bore_radius and hub_height > 0:
            hub = cylinder(hub_radius, hub_height, _segments(64, quality), center=False)
            hub = hub.translate((0, 0, thickness / 2.0))
            solid = solid + hub
            solid = solid - cylinder(bore_radius, hub_height + thickness + 2.0, _segments(64, quality))
        if lightening_holes > 0:
            solid = solid - _hole_cutter(
                count=lightening_holes,
                circle_radius=hole_circle,
                hole_radius=hole_radius,
                height=thickness + 4.0,
                quality=quality,
            )
        return solid_to_mesh(solid, name)

    return _native_ring_solid(
        outer_profile=gear_contour(teeth, pitch_radius, tooth_height),
        inner_radius=bore_radius,
        thickness=thickness,
        segments=_segments(64, quality),
        name=name,
    )


def build_helical_gear(params: Dict[str, Any], name: str = "HelicalGear") -> MeshData:
    teeth = int(params.get("teeth", 18))
    pitch_radius = float(params.get("pitch_radius", 12.0))
    thickness = float(params.get("thickness", 4.0))
    bore_radius = float(params.get("bore_radius", 3.0))
    tooth_height = float(params.get("tooth_height", max(1.5, pitch_radius * 0.12)))
    helix_angle = float(params.get("helix_angle", 20.0))
    quality = params.get("quality", "medium")

    if HAS_MANIFOLD:
        profile = gear_contour(teeth, pitch_radius, tooth_height)
        bore = circle_contour(bore_radius, _segments(64, quality))
        twist = math.degrees(2.0 * thickness * math.tan(math.radians(helix_angle)) / max(pitch_radius, 1e-6))
        solid = extrude(
            [profile, bore],
            thickness,
            twist_deg=twist,
            divisions=max(2, int(thickness * 3)),
        ).translate((0, 0, -thickness / 2.0))
        return solid_to_mesh(solid, name)

    return _native_ring_solid(
        outer_profile=gear_contour(teeth, pitch_radius, tooth_height),
        inner_radius=bore_radius,
        thickness=thickness,
        segments=_segments(64, quality),
        name=name,
    )


def build_flange(params: Dict[str, Any], name: str = "Flange") -> MeshData:
    outer = float(params.get("outer_radius", 20.0))
    inner = float(params.get("inner_radius", 8.0))
    thickness = float(params.get("thickness", 5.0))
    bolt_count = int(params.get("bolt_count", 6))
    bolt_hole = float(params.get("bolt_hole_radius", max(0.1, (outer - inner) * 0.11)))
    default_circle = (outer + inner) / 2.0 + (outer - inner) * 0.18
    bolt_circle = float(params.get("bolt_circle_radius", default_circle))
    # Los taladros deben quedar dentro del disco y fuera del barreno central
    bolt_circle = float(min(max(bolt_circle, inner + bolt_hole * 1.6), outer - bolt_hole * 1.6))
    hub_radius = float(params.get("hub_radius", 0.0))
    hub_height = float(params.get("hub_height", 0.0))
    raised_face = float(params.get("raised_face", 0.0))
    quality = params.get("quality", "medium")
    segments = _segments(80, quality)

    if outer <= inner:
        raise ValueError("outer_radius debe ser mayor que inner_radius.")

    if HAS_MANIFOLD:
        ring = extrude(
            [circle_contour(outer, segments), circle_contour(inner, segments, phase=math.pi / segments)],
            thickness,
        ).translate((0, 0, -thickness / 2.0))
        solid = ring
        if raised_face > 0:
            rf = extrude(
                [circle_contour(outer * 0.82, segments), circle_contour(inner, segments, phase=math.pi / segments)],
                raised_face,
            ).translate((0, 0, thickness / 2.0))
            solid = solid + rf
        if hub_radius > 0 and hub_height > 0:
            solid = solid + cylinder(hub_radius, hub_height, segments, center=False)
        total_h = thickness + raised_face + hub_height + 2.0
        solid = solid - cylinder(inner, total_h, segments)
        if bolt_count > 0:
            solid = solid - _hole_cutter(
                count=bolt_count,
                circle_radius=bolt_circle,
                hole_radius=bolt_hole,
                height=thickness + 8.0,
                quality=quality,
            )
        return solid_to_mesh(solid, name)

    return _native_ring_solid(
        outer_profile=circle_contour(outer, segments),
        inner_radius=inner,
        thickness=thickness,
        segments=segments,
        name=name,
    )


def build_washer(params: Dict[str, Any], name: str = "Washer") -> MeshData:
    outer = float(params.get("outer_radius", 10.0))
    inner = float(params.get("inner_radius", 5.0))
    thickness = float(params.get("thickness", 1.5))
    quality = params.get("quality", "medium")
    segments = _segments(80, quality)
    if HAS_MANIFOLD:
        ring = extrude(
            [circle_contour(outer, segments), circle_contour(inner, segments, phase=math.pi / segments)],
            thickness,
        ).translate((0, 0, -thickness / 2.0))
        return solid_to_mesh(ring, name)
    return _native_ring_solid(circle_contour(outer, segments), inner, thickness, segments, name)


def build_hex_nut(params: Dict[str, Any], name: str = "HexNut") -> MeshData:
    across_flats = float(params.get("across_flats", 17.0))
    thickness = float(params.get("thickness", 8.0))
    bore = float(params.get("bore_radius", 5.0))
    chamfer = float(params.get("chamfer", thickness * 0.06))
    quality = params.get("quality", "medium")
    segments = _segments(64, quality)

    if not HAS_MANIFOLD:
        raise RuntimeError("hex_nut requiere manifold3d (pip install manifold3d).")
    solid = extrude([hex_contour(across_flats)], thickness).translate((0, 0, -thickness / 2.0))
    solid = solid - cylinder(bore, thickness + 2.0, segments)
    if chamfer > 0:
        top = cylinder(bore, chamfer, segments, center=False, radius_top=bore + chamfer)
        bottom = cylinder(bore + chamfer, chamfer, segments, center=False, radius_top=bore)
        solid = solid - top.translate((0, 0, thickness / 2.0 - chamfer))
        solid = solid - bottom.translate((0, 0, -thickness / 2.0))
    return solid_to_mesh(solid, name)


def build_bolt(params: Dict[str, Any], name: str = "Bolt") -> MeshData:
    head_diameter = float(params.get("head_diameter", 16.0))
    head_height = float(params.get("head_height", 6.0))
    shank_diameter = float(params.get("shank_diameter", 10.0))
    length = float(params.get("length", 40.0))
    socket = bool(params.get("socket", True))
    socket_size = float(params.get("socket_size", shank_diameter * 0.55))
    quality = params.get("quality", "medium")
    segments = _segments(48, quality)

    if not HAS_MANIFOLD:
        raise RuntimeError("bolt requiere manifold3d (pip install manifold3d).")
    shank = cylinder(shank_diameter / 2.0, length, segments, center=False)
    head = extrude([hex_contour(head_diameter)], head_height).translate((0, 0, -head_height))
    solid = shank + head
    if socket:
        cutter = extrude([hex_contour(socket_size)], head_height * 0.75).translate(
            (0, 0, -head_height * 0.75 - 0.01)
        )
        solid = solid - cutter
    return solid_to_mesh(solid, name)


def build_shaft(params: Dict[str, Any], name: str = "Shaft") -> MeshData:
    diameter = float(params.get("diameter", 12.0))
    length = float(params.get("length", 60.0))
    keyway = bool(params.get("keyway", True))
    keyway_width = float(params.get("keyway_width", diameter * 0.28))
    keyway_depth = float(params.get("keyway_depth", diameter * 0.12))
    quality = params.get("quality", "medium")
    segments = _segments(64, quality)
    steps = params.get("steps") or []

    if not HAS_MANIFOLD:
        raise RuntimeError("shaft requiere manifold3d (pip install manifold3d).")
    solid = None
    z = 0.0
    for step in steps:
        d = float(step.get("diameter", diameter))
        h = float(step.get("length", length / max(1, len(steps))))
        part = cylinder(d / 2.0, h, segments, center=False).translate((0, 0, z))
        solid = part if solid is None else solid + part
        z += h
    if solid is None:
        solid = cylinder(diameter / 2.0, length, segments, center=False)
        z = length
    if keyway:
        cut = box(keyway_width, keyway_depth * 2.0, max(1.0, z * 0.6)).translate(
            (0, diameter / 2.0, z * 0.3)
        )
        solid = solid - cut
    return solid_to_mesh(solid, name)


def _build_lid(width: float, depth: float, height: float, wall: float,
               corner_radius: float) -> MeshData:
    plate = extrude(
        [rounded_rect_contour(width, depth, corner_radius, 6)],
        wall,
        fillrule_even_odd=False,
    ).translate((0, 0, height / 2.0 + wall / 2.0))
    rim = extrude(
        [
            rounded_rect_contour(width - 2 * wall, depth - 2 * wall, max(0.0, corner_radius - wall), 6),
            rounded_rect_contour(width - 4 * wall, depth - 4 * wall, max(0.0, corner_radius - 2 * wall), 6),
        ],
        3 * wall,
    ).translate((0, 0, height / 2.0 - 1.5 * wall))
    return solid_to_mesh(plate + rim, "Lid")


def build_box_enclosure(params: Dict[str, Any], name: str = "Enclosure") -> MeshData:
    width = float(params.get("width", 80.0))
    depth = float(params.get("depth", 60.0))
    height = float(params.get("height", 30.0))
    wall = float(params.get("wall_thickness", 2.4))
    corner_radius = float(params.get("corner_radius", 4.0))
    open_top = bool(params.get("open_top", True))
    lid = bool(params.get("lid", False))
    standoffs = int(params.get("standoffs", 0))
    standoff_diameter = float(params.get("standoff_diameter", 6.0))
    standoff_hole = float(params.get("standoff_hole_radius", 1.4))
    quality = params.get("quality", "medium")
    segments = _segments(32, quality)

    if not HAS_MANIFOLD:
        raise RuntimeError("box_enclosure requiere manifold3d (pip install manifold3d).")
    if wall * 2.0 >= min(width, depth) or wall >= height:
        raise ValueError("El espesor de pared es demasiado grande para las dimensiones indicadas.")

    outer_contour = rounded_rect_contour(width, depth, corner_radius, 6)
    solid = extrude([outer_contour], height, fillrule_even_odd=False).translate((0, 0, -height / 2.0))
    inner_contour = rounded_rect_contour(
        width - 2 * wall, depth - 2 * wall, max(0.0, corner_radius - wall), 6
    )
    # El vaciado deja siempre la pared inferior; si la caja es cerrada
    # también deja la superior. Antes se restaba el fondo en lugar de la boca.
    inner_height = (height - wall) if open_top else (height - 2.0 * wall)
    if inner_height > 0.1:
        inner = extrude([inner_contour], inner_height, fillrule_even_odd=False).translate(
            (0, 0, -height / 2.0 + wall)
        )
        solid = solid - inner
    if standoffs > 0:
        for i in range(standoffs):
            ang = i * TAU / standoffs
            radius = max(0.0, min(width, depth) * 0.5 - wall - standoff_diameter)
            cx, cy = math.cos(ang) * radius, math.sin(ang) * radius
            post = cylinder(standoff_diameter / 2.0, inner_height, segments, center=False).translate(
                (cx, cy, -height / 2.0 + wall)
            )
            post = post - cylinder(standoff_hole, inner_height * 1.5, 24, center=False).translate(
                (cx, cy, -height / 2.0 + wall)
            )
            solid = solid + post
    mesh = solid_to_mesh(solid, name)
    if lid:
        mesh = mesh.merged_with(_build_lid(width, depth, height, wall, corner_radius))
    return mesh


def build_l_bracket(params: Dict[str, Any], name: str = "LBracket") -> MeshData:
    leg_a = float(params.get("leg_a", 60.0))
    leg_b = float(params.get("leg_b", 40.0))
    width = float(params.get("width", 30.0))
    thickness = float(params.get("thickness", 5.0))
    hole_diameter = float(params.get("hole_diameter", 6.5))
    holes_per_leg = int(params.get("holes_per_leg", 2))
    quality = params.get("quality", "medium")
    segments = _segments(32, quality)

    if not HAS_MANIFOLD:
        raise RuntimeError("l_bracket requiere manifold3d (pip install manifold3d).")
    horizontal = box(leg_a, width, thickness).translate((0, 0, thickness / 2.0))
    vertical = box(thickness, width, leg_b).translate((-leg_a / 2.0 + thickness / 2.0, 0, leg_b / 2.0))
    solid = horizontal + vertical
    for i in range(max(1, holes_per_leg)):
        x = -leg_a / 2.0 + thickness + (i + 1) * (leg_a - thickness) / (holes_per_leg + 1)
        solid = solid - cylinder(hole_diameter / 2.0, thickness + 4.0, segments).translate(
            (x, 0, thickness / 2.0)
        )
    for i in range(max(1, holes_per_leg)):
        z = thickness + (i + 1) * (leg_b - thickness) / (holes_per_leg + 1)
        hole = cylinder(hole_diameter / 2.0, thickness + 4.0, segments)
        hole = hole.rotate((0, 1, 0)).translate((-leg_a / 2.0 + thickness / 2.0, 0, z))
        solid = solid - hole
    return solid_to_mesh(solid, name)


def build_pulley(params: Dict[str, Any], name: str = "Pulley") -> MeshData:
    outer = float(params.get("outer_radius", 25.0))
    groove_depth = float(params.get("groove_depth", 4.0))
    width = float(params.get("width", 16.0))
    bore = float(params.get("bore_radius", 6.0))
    hub_radius = float(params.get("hub_radius", outer * 0.45))
    hub_width = float(params.get("hub_width", width * 1.5))
    quality = params.get("quality", "medium")
    segments = _segments(96, quality)

    if not HAS_MANIFOLD:
        raise RuntimeError("pulley requiere manifold3d (pip install manifold3d).")
    r_root = max(bore + 1.0, outer - groove_depth)
    profile = np.array([
        [bore, -width / 2.0],
        [outer, -width / 2.0],
        [outer, -width / 4.0],
        [r_root, 0.0],
        [outer, width / 4.0],
        [outer, width / 2.0],
        [bore, width / 2.0],
    ])
    solid = revolve(profile, segments)
    if hub_width > width:
        solid = solid + cylinder(hub_radius, hub_width - width, segments, center=True)
    solid = solid - cylinder(bore, width * 3.0, segments)
    return solid_to_mesh(solid, name)


def build_bearing(params: Dict[str, Any], name: str = "Bearing") -> MeshData:
    outer = float(params.get("outer_radius", 26.0))
    inner = float(params.get("inner_radius", 10.0))
    width = float(params.get("width", 8.0))
    ball_count = int(params.get("ball_count", 9))
    ball_radius = float(params.get("ball_radius", max(1.5, (outer - inner) * 0.18)))
    quality = params.get("quality", "medium")
    segments = _segments(72, quality)

    if not HAS_MANIFOLD:
        raise RuntimeError("bearing requiere manifold3d (pip install manifold3d).")
    race = (outer - inner) / 2.0
    pitch = (outer + inner) / 2.0
    outer_ring = extrude(
        [circle_contour(outer, segments), circle_contour(outer - race * 0.55, segments, phase=math.pi / segments)],
        width,
    ).translate((0, 0, -width / 2.0))
    inner_ring = extrude(
        [circle_contour(inner + race * 0.55, segments), circle_contour(inner, segments, phase=math.pi / segments)],
        width,
    ).translate((0, 0, -width / 2.0))
    solid = outer_ring + inner_ring
    for i in range(max(3, ball_count)):
        ang = i * TAU / max(3, ball_count)
        ball = sphere(ball_radius, _segments(32, quality)).translate(
            (pitch * math.cos(ang), pitch * math.sin(ang), 0.0)
        )
        solid = solid + ball
    return solid_to_mesh(solid, name)


def build_gear_rack(params: Dict[str, Any], name: str = "GearRack") -> MeshData:
    teeth = int(params.get("teeth", 14))
    module = float(params.get("module", 3.0))
    width = float(params.get("width", 20.0))
    height = float(params.get("height", 6.0))
    hole_diameter = float(params.get("hole_diameter", 0.0))
    quality = params.get("quality", "medium")
    segments = _segments(32, quality)

    if not HAS_MANIFOLD:
        raise RuntimeError("gear_rack requiere manifold3d (pip install manifold3d).")
    contour = rack_contour(teeth, module, height)
    solid = extrude([contour], width, fillrule_even_odd=False).translate((0, 0, -width / 2.0))
    if hole_diameter > 0:
        step = teeth * module / (teeth + 1)
        for i in range(1, teeth + 1):
            x = -teeth * module / 2.0 + i * step
            solid = solid - cylinder(hole_diameter / 2.0, width * 2.0, segments).translate(
                (x, height * 0.5, 0)
            )
    return solid_to_mesh(solid, name)


def build_pipe_elbow(params: Dict[str, Any], name: str = "PipeElbow") -> MeshData:
    pipe_radius = float(params.get("radius", 7.5))
    bend_radius = float(params.get("bend_radius", 17.5))
    angle_deg = float(params.get("angle_deg", 90.0))
    segments = _segments(int(params.get("segments", 48)), params.get("quality", "medium"))
    steps = max(12, int(segments * 1.5))

    if bend_radius <= pipe_radius:
        raise ValueError("bend_radius debe ser mayor que el radio de la tubería.")
    angles = np.linspace(0.0, math.radians(angle_deg), steps)
    path = np.column_stack([
        bend_radius * np.cos(angles),
        bend_radius * np.sin(angles),
        np.zeros_like(angles),
    ])
    return sweep_tube(path, pipe_radius, segments=max(12, segments // 2), cap=True)


def build_helical_spring(params: Dict[str, Any], name: str = "HelicalSpring") -> MeshData:
    coil_radius = float(params.get("coil_radius", params.get("radius", 10.0)))
    wire_radius = float(params.get("wire_radius", 1.2))
    turns = float(params.get("turns", 5.0))
    pitch = float(params.get("pitch", 4.0))
    quality = params.get("quality", "medium")
    segments = _segments(int(params.get("segments", 24)), quality)
    steps = max(24, int(turns * _segments(48, quality)))

    t = np.linspace(0.0, turns * TAU, steps)
    path = np.column_stack([
        coil_radius * np.cos(t),
        coil_radius * np.sin(t),
        pitch * t / TAU,
    ])
    return sweep_tube(path, wire_radius, segments=max(8, segments // 2), cap=True)


def build_plate(params: Dict[str, Any], name: str = "Plate") -> MeshData:
    width = float(params.get("width", 100.0))
    depth = float(params.get("depth", 60.0))
    thickness = float(params.get("thickness", 5.0))
    corner_radius = float(params.get("corner_radius", 5.0))
    hole_count = int(params.get("hole_count", 4))
    hole_diameter = float(params.get("hole_diameter", 5.5))
    hole_margin = float(params.get("hole_margin", 10.0))
    quality = params.get("quality", "medium")
    segments = _segments(32, quality)

    if not HAS_MANIFOLD:
        raise RuntimeError("plate requiere manifold3d (pip install manifold3d).")
    solid = extrude(
        [rounded_rect_contour(width, depth, corner_radius, 6)], thickness, fillrule_even_odd=False
    ).translate((0, 0, -thickness / 2.0))
    if hole_count > 0:
        positions = [(-1, -1), (1, -1), (1, 1), (-1, 1), (0, 0)][: max(1, min(5, hole_count))]
        for sx, sy in positions:
            x = sx * (width / 2.0 - hole_margin)
            y = sy * (depth / 2.0 - hole_margin)
            solid = solid - cylinder(hole_diameter / 2.0, thickness + 4.0, segments).translate((x, y, 0))
    return solid_to_mesh(solid, name)


def build_box(params: Dict[str, Any], name: str = "Box") -> MeshData:
    w = float(params.get("width", 30.0))
    d = float(params.get("depth", 20.0))
    h = float(params.get("height", 15.0))
    if HAS_MANIFOLD:
        return solid_to_mesh(
            extrude(
                [rounded_rect_contour(w, d, float(params.get("corner_radius", 0.0)), 6)],
                h,
                fillrule_even_odd=False,
            ).translate((0, 0, -h / 2.0)),
            name,
        )
    verts = np.array([
        [-w / 2, -d / 2, -h / 2], [w / 2, -d / 2, -h / 2], [w / 2, d / 2, -h / 2], [-w / 2, d / 2, -h / 2],
        [-w / 2, -d / 2, h / 2], [w / 2, -d / 2, h / 2], [w / 2, d / 2, h / 2], [-w / 2, d / 2, h / 2],
    ])
    faces = np.array([
        [0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6],
        [0, 4, 7], [0, 7, 3], [1, 2, 6], [1, 6, 5],
    ])
    return MeshData(verts, faces, name)


def build_cylinder(params: Dict[str, Any], name: str = "Cylinder") -> MeshData:
    radius = float(params.get("radius", 15.0))
    height = float(params.get("height", 30.0))
    bore = float(params.get("bore_radius", 0.0))
    segments = _segments(int(params.get("segments", 64)), params.get("quality", "medium"))
    if HAS_MANIFOLD:
        solid = cylinder(radius, height, segments)
        if bore > 0:
            solid = solid - cylinder(bore, height + 2.0, segments)
        return solid_to_mesh(solid, name)
    return _native_ring_solid(circle_contour(radius, segments), max(1e-3, bore), height, segments, name)


def _native_ring_solid(outer_profile: np.ndarray, inner_radius: float,
                       thickness: float, segments: int, name: str = "ring") -> MeshData:
    """Anillo nativo: perfil exterior arbitrario + agujero circular (sin manifold)."""
    outer = np.asarray(outer_profile, dtype=float)
    n = len(outer)
    angles = np.arctan2(outer[:, 1], outer[:, 0])
    inner = np.column_stack([np.cos(angles) * inner_radius, np.sin(angles) * inner_radius])

    half_t = thickness / 2.0
    top_out = np.column_stack([outer, np.full(n, half_t)])
    top_in = np.column_stack([inner, np.full(n, half_t)])
    bot_out = np.column_stack([outer, np.full(n, -half_t)])
    bot_in = np.column_stack([inner, np.full(n, -half_t)])
    verts = np.vstack([top_out, top_in, bot_out, bot_in])

    ito = np.arange(n)
    iti = np.arange(n) + n
    ibo = np.arange(n) + 2 * n
    ibi = np.arange(n) + 3 * n

    faces: List[Tuple[int, int, int]] = []
    for i in range(n):
        j = (i + 1) % n
        faces.append((ito[i], ito[j], iti[i]))
        faces.append((ito[j], iti[j], iti[i]))
        faces.append((ibo[i], ibi[i], ibo[j]))
        faces.append((ibo[j], ibi[i], ibi[j]))
        faces.append((ito[i], ibo[i], ito[j]))
        faces.append((ito[j], ibo[i], ibo[j]))
        faces.append((iti[i], iti[j], ibi[i]))
        faces.append((iti[j], ibi[j], ibi[i]))

    return MeshData(verts, np.asarray(faces, dtype=np.int64), name)


# ---------------------------------------------------------------------------
# DISPATCH DE PIEZAS
# ---------------------------------------------------------------------------
PART_BUILDERS = {
    "spur_gear": build_spur_gear,
    "helical_gear": build_helical_gear,
    "flange": build_flange,
    "washer": build_washer,
    "hex_nut": build_hex_nut,
    "bolt": build_bolt,
    "shaft": build_shaft,
    "box_enclosure": build_box_enclosure,
    "l_bracket": build_l_bracket,
    "pulley": build_pulley,
    "bearing": build_bearing,
    "gear_rack": build_gear_rack,
    "pipe_elbow": build_pipe_elbow,
    "helical_spring": build_helical_spring,
    "plate": build_plate,
    "box": build_box,
    "cylinder": build_cylinder,
}

PART_ALIASES = {
    "gear": "spur_gear",
    "engranaje": "spur_gear",
    "helical": "helical_gear",
    "brida": "flange",
    "arandela": "washer",
    "tuerca": "hex_nut",
    "nut": "hex_nut",
    "perno": "bolt",
    "tornillo": "bolt",
    "eje": "shaft",
    "carcasa": "box_enclosure",
    "enclosure": "box_enclosure",
    "soporte": "l_bracket",
    "bracket": "l_bracket",
    "polea": "pulley",
    "rodamiento": "bearing",
    "cremallera": "gear_rack",
    "rack": "gear_rack",
    "codo": "pipe_elbow",
    "elbow": "pipe_elbow",
    "resorte": "helical_spring",
    "spring": "helical_spring",
    "placa": "plate",
    "caja": "box",
    "cilindro": "cylinder",
}

#: Catálogo legible de piezas y sus parámetros principales (para prompts/metadata).
PART_CATALOG: Dict[str, Dict[str, Any]] = {
    "spur_gear": {
        "label": "Engranaje recto",
        "params": ["teeth", "pitch_radius", "thickness", "bore_radius", "tooth_height",
                   "hub_radius", "hub_height", "lightening_holes", "hole_radius"],
    },
    "helical_gear": {
        "label": "Engranaje helicoidal",
        "params": ["teeth", "pitch_radius", "thickness", "bore_radius", "helix_angle"],
    },
    "flange": {
        "label": "Brida de tubería",
        "params": ["outer_radius", "inner_radius", "thickness", "bolt_count",
                   "bolt_circle_radius", "bolt_hole_radius", "hub_radius", "hub_height", "raised_face"],
    },
    "washer": {"label": "Arandela", "params": ["outer_radius", "inner_radius", "thickness"]},
    "hex_nut": {"label": "Tuerca hexagonal", "params": ["across_flats", "thickness", "bore_radius", "chamfer"]},
    "bolt": {"label": "Perno/tornillo", "params": ["head_diameter", "head_height", "shank_diameter", "length", "socket", "socket_size"]},
    "shaft": {"label": "Eje con chavetero", "params": ["diameter", "length", "keyway", "keyway_width", "keyway_depth", "steps"]},
    "box_enclosure": {"label": "Carcasa hueca", "params": ["width", "depth", "height", "wall_thickness", "corner_radius", "open_top", "lid", "standoffs", "standoff_diameter", "standoff_hole_radius"]},
    "l_bracket": {"label": "Escuadra en L", "params": ["leg_a", "leg_b", "width", "thickness", "hole_diameter", "holes_per_leg"]},
    "pulley": {"label": "Polea trapezoidal", "params": ["outer_radius", "groove_depth", "width", "bore_radius", "hub_radius", "hub_width"]},
    "bearing": {"label": "Rodamiento", "params": ["outer_radius", "inner_radius", "width", "ball_count", "ball_radius"]},
    "gear_rack": {"label": "Cremallera", "params": ["teeth", "module", "width", "height", "hole_diameter"]},
    "pipe_elbow": {"label": "Codo de tubería", "params": ["radius", "bend_radius", "angle_deg", "segments"]},
    "helical_spring": {"label": "Resorte helicoidal", "params": ["coil_radius", "wire_radius", "turns", "pitch", "segments"]},
    "plate": {"label": "Placa con taladros", "params": ["width", "depth", "thickness", "corner_radius", "hole_count", "hole_diameter", "hole_margin"]},
    "box": {"label": "Bloque rectangular", "params": ["width", "depth", "height", "corner_radius"]},
    "cylinder": {"label": "Cilindro/tubo", "params": ["radius", "height", "bore_radius", "segments"]},
}


def normalize_model_type(model_type: str) -> str:
    key = str(model_type or "spur_gear").strip().lower().replace("-", "_").replace(" ", "_")
    return PART_ALIASES.get(key, key)


def list_part_types() -> List[str]:
    return list(PART_BUILDERS.keys())


def build_part(model_type: str, params: Optional[Dict[str, Any]] = None,
               name: Optional[str] = None) -> Tuple[MeshData, Dict[str, Any]]:
    """Construye una pieza real y devuelve (malla, metadata)."""
    key = normalize_model_type(model_type)
    if key not in PART_BUILDERS:
        raise ValueError(
            "Tipo de pieza '" + str(model_type) + "' no soportado. "
            "Disponibles: " + ", ".join(sorted(PART_BUILDERS)) + "."
        )
    clean_params = dict(params or {})
    mesh = PART_BUILDERS[key](clean_params, name=name or key)
    meta = {
        "model_type": key,
        "engine": "manifold3d" if HAS_MANIFOLD else "native",
        "units": "mm",
        "params": clean_params,
        "volume_mm3": round(mesh.volume(), 3),
        "bounds_mm": {
            "min": [round(float(v), 3) for v in mesh.bounds[0]],
            "max": [round(float(v), 3) for v in mesh.bounds[1]],
        },
        "watertight": mesh.is_watertight(),
    }
    return mesh, meta
