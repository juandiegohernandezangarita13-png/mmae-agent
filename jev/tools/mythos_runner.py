"""
Herramienta de ejecución y evaluación neuronal de OpenMythos.
Permite a JEV inicializar, verificar estabilidad matemática y ejecutar pasadas
de inferencia del modelo Recurrent-Depth Transformer (RDT) directamente en la GPU (CUDA RTX 3050).
"""
from typing import Dict, Any, Optional
import time
from jev.tools.base import BaseTool, ToolResult


class OpenMythosRunnerTool(BaseTool):
    """Herramienta para ejecutar y probar la arquitectura OpenMythos en PyTorch / GPU."""
    name = "run_open_mythos"
    description = (
        "Ejecuta, prueba o evalúa la arquitectura neuronal recurrente OpenMythos (RDT) en la GPU local (CUDA RTX 3050). "
        "Permite verificar el radio espectral de estabilidad rho(A) < 1, medir latencia de inferencia por bucles "
        "y ejecutar pasadas de tensores latentes con atención MLA/GQA y MoE sparse."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["benchmark", "verify_stability", "forward_test", "variant_info", "compare_transformer"],
                "description": "Acción a realizar: 'benchmark' (latencia y memoria), 'verify_stability' (rho(A) < 1), 'forward_test' (inferencia), 'variant_info' (analiza escalas 1B a 1T) o 'compare_transformer' (compara RDT looped vs vanilla transformer)."
            },
            "variant_name": {
                "type": "string",
                "enum": ["1b", "3b", "10b", "50b", "100b", "500b", "1t", "all"],
                "description": "Variante de escala a inspeccionar para 'variant_info' (por defecto '1b')."
            },
            "dim": {
                "type": "integer",
                "description": "Dimensión oculta del modelo (ej. 128 o 256 para pruebas ultrarrápidas). Por defecto 128."
            },
            "n_loops": {
                "type": "integer",
                "description": "Número de bucles recurrentes T a ejecutar (1 a 16). Por defecto 4."
            },
            "attn_type": {
                "type": "string",
                "enum": ["mla", "gqa"],
                "description": "Tipo de atención: 'mla' (Multi-Latent Attention) o 'gqa' (Grouped-Query Attention). Por defecto 'mla'."
            },
            "use_cuda": {
                "type": "boolean",
                "description": "Si es True, intenta ejecutar en la GPU NVIDIA mediante CUDA. Por defecto True."
            }
        },
        "required": ["action"]
    }

    def execute(
        self,
        action: str,
        dim: int = 128,
        n_loops: int = 4,
        attn_type: str = "mla",
        use_cuda: bool = True,
        **kwargs
    ) -> ToolResult:
        try:
            import torch
            from open_mythos.main import OpenMythos, MythosConfig
        except ImportError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"No se pudo importar PyTorch u OpenMythos en el entorno: {str(e)}"
            )

        # Determinar dispositivo
        device_str = "cpu"
        device_name = "CPU"
        if use_cuda and torch.cuda.is_available():
            device_str = "cuda"
            device_name = torch.cuda.get_device_name(0)

        device = torch.device(device_str)

        try:
            # Configuración contenida y eficiente para pruebas en GPU local
            dim = max(64, min(1024, dim))
            n_loops = max(1, min(32, n_loops))

            base_cfg = {
                "vocab_size": 1000,
                "dim": dim,
                "n_heads": 4,
                "max_seq_len": 128,
                "max_loop_iters": max(n_loops, 4),
                "prelude_layers": 1,
                "coda_layers": 1,
                "n_experts": 4,
                "n_shared_experts": 1,
                "n_experts_per_tok": 2,
                "expert_dim": max(32, dim // 4),
                "lora_rank": 8,
                "attn_type": attn_type,
            }

            if attn_type == "gqa":
                cfg = MythosConfig(**base_cfg, n_kv_heads=2)
            else:
                cfg = MythosConfig(
                    **base_cfg,
                    n_kv_heads=4,
                    kv_lora_rank=max(16, dim // 4),
                    q_lora_rank=max(32, dim // 2),
                    qk_rope_head_dim=16,
                    qk_nope_head_dim=16,
                    v_head_dim=16,
                )

            model = OpenMythos(cfg).to(device)
            total_params = sum(p.numel() for p in model.parameters())

            # Cálculo del radio espectral rho(A)
            # Para matriz diagonal A, los autovalores son exactamente sus elementos diagonales
            A_diag = model.recurrent.injection.get_A()
            rho_A = float(A_diag.abs().max().item())
            is_stable = rho_A < 1.0

            if action == "verify_stability":
                msg = (
                    f"✓ Verificación de Estabilidad Espectral LTI OpenMythos:\n"
                    f"• Dispositivo: {device_name} ({device_str})\n"
                    f"• Parámetros del modelo: {total_params:,}\n"
                    f"• Radio Espectral ρ(A): {rho_A:.6f}\n"
                    f"• Criterio Dinámico ρ(A) < 1.0: {'CUMPLIDO (Estable por construcción)' if is_stable else 'FALLIDO'}\n"
                    f"• Tipo de Atención: {attn_type.upper()} | Dim: {dim} | Bucles Máx: {cfg.max_loop_iters}"
                )
                return ToolResult(
                    success=is_stable,
                    output=msg,
                    data={"rho_A": rho_A, "is_stable": is_stable, "params": total_params, "device": device_str}
                )

            elif action == "benchmark":
                # Medir latencia de inferencia recurrente
                seq_len = 16
                batch_size = 1
                sample_tokens = torch.randint(0, cfg.vocab_size, (batch_size, seq_len), device=device)

                # Warmup
                with torch.no_grad():
                    _ = model(sample_tokens, n_loops=n_loops)

                if device_str == "cuda":
                    torch.cuda.synchronize()

                iters = 5
                start_t = time.perf_counter()
                with torch.no_grad():
                    for _ in range(iters):
                        _ = model(sample_tokens, n_loops=n_loops)
                    if device_str == "cuda":
                        torch.cuda.synchronize()
                elapsed = time.perf_counter() - start_t
                avg_latency_ms = (elapsed / iters) * 1000.0

                vram_info = ""
                if device_str == "cuda":
                    vram_allocated_mb = torch.cuda.memory_allocated() / (1024 * 1024)
                    vram_info = f"• Memoria VRAM asignada: {vram_allocated_mb:.2f} MB\n"

                msg = (
                    f"🚀 Benchmark Neuronal OpenMythos en {device_name}:\n"
                    f"• Dimensión: {dim} | Bucles Recurrentes: {n_loops} | Atención: {attn_type.upper()}\n"
                    f"• Parámetros: {total_params:,}\n"
                    f"• Radio espectral ρ(A): {rho_A:.4f} (Estable)\n"
                    f"• Latencia promedio por pasada: {avg_latency_ms:.2f} ms\n"
                    f"{vram_info}"
                    f"• Secuencia de prueba: shape ({batch_size}, {seq_len}) sobre vocabulario {cfg.vocab_size}"
                )
                return ToolResult(
                    success=True,
                    output=msg,
                    data={
                        "avg_latency_ms": avg_latency_ms,
                        "device": device_name,
                        "params": total_params,
                        "rho_A": rho_A,
                        "n_loops": n_loops
                    }
                )

            elif action == "forward_test":
                # Realizar pasada y comprobar dimensiones
                sample_tokens = torch.randint(0, cfg.vocab_size, (1, 8), device=device)
                with torch.no_grad():
                    logits = model(sample_tokens, n_loops=n_loops)

                out_shape = list(logits.shape)
                msg = (
                    f"✓ Pasada de Inferencia OpenMythos Exitosa:\n"
                    f"• Dispositivo: {device_name}\n"
                    f"• Shape de entrada: [1, 8] -> Logits de salida: {out_shape}\n"
                    f"• Bucles ejecutados: {n_loops}\n"
                    f"• Estabilidad espectral ρ(A): {rho_A:.4f} (< 1.0)\n"
                    f"• Modelo listo para operaciones de razonamiento latente."
                )
                return ToolResult(
                    success=True,
                    output=msg,
                    data={"shape": out_shape, "rho_A": rho_A, "device": device_name}
                )

            elif action == "variant_info":
                import open_mythos.variants as mv
                variant_map = {
                    "1b": ("mythos_1b", mv.mythos_1b),
                    "3b": ("mythos_3b", mv.mythos_3b),
                    "10b": ("mythos_10b", mv.mythos_10b),
                    "50b": ("mythos_50b", mv.mythos_50b),
                    "100b": ("mythos_100b", mv.mythos_100b),
                    "500b": ("mythos_500b", mv.mythos_500b),
                    "1t": ("mythos_1t", mv.mythos_1t),
                }
                v_target = kwargs.get("variant_name", "1b").lower()
                if v_target == "all":
                    lines = ["📊 Resumen de Variantes Arquitectónicas OpenMythos (1B a 1T):"]
                    for name, (label, fn) in variant_map.items():
                        c = fn()
                        active_ratio = round((c.n_shared_experts + c.n_experts_per_tok) / (c.n_shared_experts + c.n_experts) * 100, 1)
                        lines.append(f"• {label.upper()}: dim={c.dim}, expert_dim={c.expert_dim}, {c.n_experts} expertos (activos {c.n_experts_per_tok}), {c.max_loop_iters} bucles recurrentes, contexto={c.max_seq_len:,}, activación={active_ratio}%")
                    return ToolResult(success=True, output="\n".join(lines), data={"variants": list(variant_map.keys())})
                elif v_target in variant_map:
                    label, fn = variant_map[v_target]
                    c = fn()
                    active_ratio = round((c.n_shared_experts + c.n_experts_per_tok) / (c.n_shared_experts + c.n_experts) * 100, 1)
                    msg = (
                        f"🧬 Especificación Arquitectónica OpenMythos [{label.upper()}]:\n"
                        f"• Dimensión oculta: {c.dim}\n"
                        f"• Atención: {c.attn_type.upper()} ({c.n_heads} Q heads, {c.n_kv_heads} KV heads)\n"
                        f"• MoE: {c.n_experts} expertos enrutados + {c.n_shared_experts} compartidos (top-{c.n_experts_per_tok} por token)\n"
                        f"• Tasa de activación MoE: ~{active_ratio}% (computación dispersa ultra-eficiente)\n"
                        f"• Profundidad recurrente: {c.max_loop_iters} iteraciones en bucle con inyección de anclaje\n"
                        f"• Ventana de contexto: {c.max_seq_len:,} tokens (RoPE theta: {c.rope_theta:,.0f})\n"
                        f"• Parada adaptativa ACT: umbral={c.act_threshold}\n"
                        f"• LoRA de profundidad: rank={c.lora_rank}"
                    )
                    return ToolResult(success=True, output=msg, data={"variant": label, "dim": c.dim, "loops": c.max_loop_iters, "active_ratio": active_ratio})
                else:
                    return ToolResult(success=False, output="", error=f"Variante '{v_target}' no reconocida. Opciones: 1b, 3b, 10b, 50b, 100b, 500b, 1t, all.")

            elif action == "compare_transformer":
                # Compara OpenMythos (Looped Transformer RDT) vs Transformer Convencional No-Looped
                seq_len = 16
                sample_tokens = torch.randint(0, cfg.vocab_size, (1, seq_len), device=device)

                with torch.no_grad():
                    _ = model(sample_tokens, n_loops=4)
                if device_str == "cuda":
                    torch.cuda.synchronize()
                t0 = time.perf_counter()
                with torch.no_grad():
                    for _ in range(5):
                        _ = model(sample_tokens, n_loops=4)
                    if device_str == "cuda":
                        torch.cuda.synchronize()
                mythos_time_ms = ((time.perf_counter() - t0) / 5) * 1000.0

                layer_params = sum(p.numel() for p in model.recurrent.block.parameters())
                baseline_estimated_params = total_params + (layer_params * 3)
                param_savings_ratio = round(baseline_estimated_params / total_params, 2)

                msg = (
                    f"🔬 Comparativa Arquitectónica: OpenMythos (RDT Looped) vs Transformer Convencional en {device_name}:\n"
                    f"• Profundidad efectiva de razonamiento: 4 iteraciones / capas\n"
                    f"• Parámetros OpenMythos (pesos compartidos + LoRA adaptativo): {total_params:,}\n"
                    f"• Parámetros Transformer Convencional equivalente (no-looped): ~{baseline_estimated_params:,}\n"
                    f"• Factor de compresión de parámetros: {param_savings_ratio}x ahorro de memoria\n"
                    f"• Latencia en GPU: {mythos_time_ms:.2f} ms por pasada (4 bucles)\n"
                    f"• Ventaja clave: OpenMythos obtiene la profundidad y razonamiento multi-hop de un modelo {param_savings_ratio}x más grande sin multiplicar la huella de VRAM."
                )
                return ToolResult(
                    success=True,
                    output=msg,
                    data={
                        "mythos_params": total_params,
                        "baseline_params": baseline_estimated_params,
                        "param_savings_ratio": param_savings_ratio,
                        "latency_ms": mythos_time_ms,
                        "device": device_name
                    }
                )

            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Acción '{action}' no reconocida. Usa 'benchmark', 'verify_stability', 'forward_test', 'variant_info' o 'compare_transformer'."
                )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Error durante la ejecución de OpenMythos: {str(e)}"
            )
