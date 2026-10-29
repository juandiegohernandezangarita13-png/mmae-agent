"""
Analizador Estocástico y Combinatorio (Lottery & Monte Carlo Engine).
Implementa:
1. Distribución hipergeométrica analítica para probabilidades exactas y cuotas (odds).
2. Prueba de bondad de ajuste Chi-cuadrado (χ²) para contrastar equiprobabilidad de la urna.
3. Clasificación de números calientes y fríos, y cálculo de Entropía de Shannon de la serie.
4. Generador de Sistemas Reducidos (Lottery Wheels / Covering Designs) con algoritmo voraz de cobertura mínima.
5. Simulador de Monte Carlo para calcular el Valor Esperado (EV) y probabilidad de ganancia neta en función del bote.
"""
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path
import math
import json
import csv
import numpy as np

try:
    from scipy import stats
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

from jev.tools.base import BaseTool, ToolResult
from jev.config import default_config


class CombinatorialAnalyticsTool(BaseTool):
    """Herramienta de análisis estocástico, combinatoria y simulación Monte Carlo."""
    name = "skill_combinatorial_analytics"
    description = (
        "Motor de analítica estocástica y combinatoria avanzada. Modela probabilidades mediante distribuciones "
        "hipergeométricas exactas, contrasta uniformidad con bondad de ajuste Chi-cuadrado, analiza entropía de Shannon, "
        "diseña sistemas reducidos (Lottery Wheels) y calcula el Valor Esperado (EV) con simulaciones de Monte Carlo."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Acción analítica: 'full_analysis', 'hypergeometric_odds', 'analyze_history', 'monte_carlo_ev', 'generate_reduced_wheel'",
                "enum": ["full_analysis", "hypergeometric_odds", "analyze_history", "monte_carlo_ev", "generate_reduced_wheel"],
                "default": "full_analysis"
            },
            "total_numbers": {
                "type": "integer",
                "description": "Cantidad total de números en la urna o bombo (población N, ej. 49 o 50)",
                "default": 49
            },
            "pick_count": {
                "type": "integer",
                "description": "Cantidad de números extraídos por sorteo (muestra k, ej. 6 o 5)",
                "default": 6
            },
            "history_file": {
                "type": "string",
                "description": "Ruta opcional a un archivo CSV o JSON con el histórico de sorteos",
                "default": ""
            },
            "history_data": {
                "type": "array",
                "description": "Lista de sorteos históricos pasados en memoria (ej. [[3, 12, 19, 24, 38, 45], ...])",
                "default": []
            },
            "jackpot": {
                "type": "number",
                "description": "Bote acumulado o premio mayor para el acierto máximo (k de k)",
                "default": 10000000.0
            },
            "ticket_price": {
                "type": "number",
                "description": "Coste monetario por cada apuesta individual",
                "default": 2.5
            },
            "secondary_prizes": {
                "type": "object",
                "description": "Premios fijos o estimados para aciertos secundarios (ej. {'5': 2500, '4': 100, '3': 10})",
                "default": {}
            },
            "tax_rate": {
                "type": "number",
                "description": "Retención fiscal o impuestos sobre ganancias superiores al límite exento (ej. 0.20 para 20%)",
                "default": 0.20
            },
            "monte_carlo_sims": {
                "type": "integer",
                "description": "Número de iteraciones aleatorias para la simulación Monte Carlo",
                "default": 25000
            },
            "wheel_numbers": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Conjunto de números seleccionados para generar el sistema reducido (tamaño > k)",
                "default": []
            },
            "wheel_guarantee": {
                "type": "integer",
                "description": "Acierto mínimo garantizado si la combinación ganadora cae en los números elegidos (ej. 4 o 5)",
                "default": 4
            }
        },
        "required": ["action"]
    }

    def __init__(self, workspace_dir: Optional[Path] = None):
        self.workspace_dir = workspace_dir or default_config.workspace_dir

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "full_analysis")
        total_n = int(kwargs.get("total_numbers", 49))
        pick_k = int(kwargs.get("pick_count", 6))
        hist_file = kwargs.get("history_file", "")
        hist_data = kwargs.get("history_data") or []
        jackpot = float(kwargs.get("jackpot", 10000000.0))
        ticket_price = float(kwargs.get("ticket_price", 2.5))
        sec_prizes = kwargs.get("secondary_prizes") or {
            str(pick_k - 1): 2500.0,
            str(pick_k - 2): 100.0,
            str(pick_k - 3): 10.0
        }
        tax_rate = float(kwargs.get("tax_rate", 0.20))
        sims = int(kwargs.get("monte_carlo_sims", 25000))
        wheel_nums = kwargs.get("wheel_numbers") or []
        wheel_guar = int(kwargs.get("wheel_guarantee", 4))

        try:
            results = {}

            # Cargar histórico si se provee
            loaded_history = self._load_history(hist_file, hist_data)

            # 1. Distribución Hipergeométrica
            if action in ("full_analysis", "hypergeometric_odds", "monte_carlo_ev"):
                odds = self.calculate_hypergeometric_odds(total_n, pick_k)
                results["hypergeometric_odds"] = odds

            # 2. Análisis Estadístico de Histórico
            if action in ("full_analysis", "analyze_history"):
                if loaded_history:
                    stat_analysis = self.analyze_history(loaded_history, total_n, pick_k)
                    results["historical_analysis"] = stat_analysis
                else:
                    results["historical_analysis"] = {
                        "notice": "No se suministraron sorteos históricos. Se omite Chi-cuadrado y entropía."
                    }

            # 3. Simulación de Monte Carlo y EV
            if action in ("full_analysis", "monte_carlo_ev"):
                ev_data = self.simulate_monte_carlo_ev(
                    total_n=total_n,
                    pick_k=pick_k,
                    jackpot=jackpot,
                    ticket_price=ticket_price,
                    secondary_prizes=sec_prizes,
                    tax_rate=tax_rate,
                    simulations=sims
                )
                results["monte_carlo_ev"] = ev_data

            # 4. Generación de Sistema Reducido
            if action in ("full_analysis", "generate_reduced_wheel") or wheel_nums:
                target_nums = wheel_nums if wheel_nums else list(range(1, min(total_n + 1, pick_k + 5)))
                wheel_data = self.generate_reduced_wheel(
                    numbers=target_nums,
                    pick_k=pick_k,
                    guarantee=wheel_guar
                )
                results["reduced_wheel"] = wheel_data

            output_summary = self._build_text_summary(action, results)

            return ToolResult(
                success=True,
                output=output_summary,
                data=results
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Error en analítica estocástica y combinatoria: {str(e)}"
            )

    # -------------------------------------------------------------------------
    # MATEMÁTICA HIPERGEOMÉTRICA
    # -------------------------------------------------------------------------
    def calculate_hypergeometric_odds(self, N: int, k: int) -> Dict[str, Any]:
        """
        Calcula las probabilidades hipergeométricas analíticas exactas para cada
        categoría de aciertos x de k en una urna de tamaño N.
        P(X = x) = [Comb(k, x) * Comb(N - k, k - x)] / Comb(N, k)
        """
        total_combinations = math.comb(N, k)
        table = []

        for x in range(k, -1, -1):
            fav = math.comb(k, x) * math.comb(N - k, k - x)
            prob = fav / total_combinations
            odds_1_in = (1.0 / prob) if prob > 0 else float('inf')

            table.append({
                "hits": x,
                "favorable_combinations": fav,
                "probability": float(prob),
                "probability_percent": float(round(prob * 100, 6)),
                "odds_1_in": float(round(odds_1_in, 2)) if odds_1_in != float('inf') else None
            })

        return {
            "population_N": N,
            "sample_k": k,
            "total_space_size": total_combinations,
            "distribution": table
        }

    # -------------------------------------------------------------------------
    # ANÁLISIS DE FRECUENCIAS HISTÓRICAS, CHI-CUADRADO Y ENTROPÍA
    # -------------------------------------------------------------------------
    def analyze_history(
        self,
        draws: List[List[int]],
        N: int,
        k: int
    ) -> Dict[str, Any]:
        """
        Analiza una serie histórica de sorteos:
        - Prueba de bondad de ajuste Chi-cuadrado frente a distribución uniforme.
        - Entropía de Shannon de la serie frente a entropía máxima.
        - Números más frecuentes (calientes) y menos frecuentes (fríos).
        """
        num_draws = len(draws)
        if num_draws == 0:
            return {"error": "Sin datos de sorteos"}

        # Conteo de frecuencias observadas
        counts = {i: 0 for i in range(1, N + 1)}
        for draw in draws:
            for num in draw:
                if 1 <= num <= N:
                    counts[num] += 1

        total_observations = num_draws * k
        expected_frequency = total_observations / N

        # Chi-cuadrado: sum((O - E)^2 / E)
        observed_arr = np.array([counts[i] for i in range(1, N + 1)], dtype=np.float64)
        expected_arr = np.full(N, expected_frequency, dtype=np.float64)

        chi2_stat = float(np.sum((observed_arr - expected_arr) ** 2 / expected_arr))
        degrees_of_freedom = N - 1

        # p-value
        if SCIPY_AVAILABLE:
            p_value = float(stats.chi2.sf(chi2_stat, degrees_of_freedom))
        else:
            # Aproximación de Wilson-Hilferty para Chi-cuadrado
            s = 2.0 / (9.0 * degrees_of_freedom)
            z = ((chi2_stat / degrees_of_freedom) ** (1/3) - (1 - s)) / math.sqrt(s)
            p_value = float(0.5 * math.erfc(z / math.sqrt(2)))

        # Entropía de Shannon: H = -sum(p_i * log2(p_i))
        probs = observed_arr / total_observations
        non_zero_probs = probs[probs > 0]
        shannon_entropy = float(-np.sum(non_zero_probs * np.log2(non_zero_probs)))
        max_entropy = float(math.log2(N))
        relative_entropy = float(shannon_entropy / max_entropy) if max_entropy > 0 else 1.0

        # Números calientes y fríos
        sorted_by_freq = sorted(counts.items(), key=lambda item: item[1], reverse=True)
        top_k = min(10, N // 2)
        hot_numbers = [{"number": num, "frequency": freq, "ratio": round(freq / expected_frequency, 3)}
                       for num, freq in sorted_by_freq[:top_k]]
        cold_numbers = [{"number": num, "frequency": freq, "ratio": round(freq / expected_frequency, 3)}
                        for num, freq in sorted_by_freq[-top_k:]]

        # Evaluación de la hipótesis de equiprobabilidad (H0)
        is_uniform = bool(p_value >= 0.05)

        return {
            "total_draws_analyzed": num_draws,
            "expected_frequency_per_number": round(expected_frequency, 2),
            "chi_square_test": {
                "statistic": round(chi2_stat, 4),
                "degrees_of_freedom": degrees_of_freedom,
                "p_value": round(p_value, 6),
                "is_uniform_at_95_conf": is_uniform,
                "verdict": "Compatible con urna perfectamente aleatoria" if is_uniform else "Desviación estadísticamente significativa detectada"
            },
            "shannon_entropy": {
                "observed_entropy_bits": round(shannon_entropy, 4),
                "theoretical_max_bits": round(max_entropy, 4),
                "entropy_efficiency": round(relative_entropy, 4)
            },
            "hot_numbers": hot_numbers,
            "cold_numbers": cold_numbers
        }

    # -------------------------------------------------------------------------
    # SIMULACIÓN MONTE CARLO Y VALOR ESPERADO (EV)
    # -------------------------------------------------------------------------
    def simulate_monte_carlo_ev(
        self,
        total_n: int,
        pick_k: int,
        jackpot: float,
        ticket_price: float,
        secondary_prizes: Dict[str, float],
        tax_rate: float = 0.20,
        simulations: int = 25000
    ) -> Dict[str, Any]:
        """
        Calcula analítica y empíricamente el Valor Esperado (EV) de una apuesta individual
        y realiza una simulación de Monte Carlo para medir volatilidad y retorno real.
        """
        total_comb = math.comb(total_n, pick_k)

        # Mapa de premios netos post-impuestos
        prizes_net = {}
        for hits_str, prize_val in secondary_prizes.items():
            h = int(hits_str)
            p = float(prize_val)
            prizes_net[h] = p * (1.0 - tax_rate) if p > 2500 else p

        # Premio mayor (Jackpot)
        prizes_net[pick_k] = jackpot * (1.0 - tax_rate)

        # 1. Cálculo analítico exacto de EV
        analytical_ev = -ticket_price
        ev_breakdown = {}
        for x in range(1, pick_k + 1):
            prob = (math.comb(pick_k, x) * math.comb(total_n - pick_k, pick_k - x)) / total_comb
            net_p = prizes_net.get(x, 0.0)
            contrib = prob * net_p
            analytical_ev += contrib
            ev_breakdown[f"{x}_hits"] = {
                "probability": float(prob),
                "net_prize": net_p,
                "ev_contribution": float(round(contrib, 6))
            }

        # 2. Simulación de Monte Carlo vectorial rápida
        # Se genera un boleto fijo de prueba [1, 2, ..., k]
        fixed_ticket = set(range(1, pick_k + 1))
        sims_to_run = min(max(simulations, 1000), 100000)

        # Muestreo aleatorio de sorteos
        # Para alta eficiencia numérica, usamos np.random.choice o hipergeométrica empírica
        # La distribución de aciertos de un boleto fijo sigue exactamente hipergeométrica
        if SCIPY_AVAILABLE:
            hits_sample = stats.hypergeom.rvs(total_n, pick_k, pick_k, size=sims_to_run)
        else:
            # Fallback a generador numpy
            probs_list = [
                (math.comb(pick_k, x) * math.comb(total_n - pick_k, pick_k - x)) / total_comb
                for x in range(pick_k + 1)
            ]
            hits_sample = np.random.choice(np.arange(pick_k + 1), size=sims_to_run, p=probs_list)

        # Calcular retornos
        payouts = np.zeros(sims_to_run, dtype=np.float64)
        hit_counts = {}
        for x in range(pick_k + 1):
            mask = (hits_sample == x)
            hit_counts[x] = int(np.sum(mask))
            if x in prizes_net:
                payouts[mask] = prizes_net[x]

        total_spent = sims_to_run * ticket_price
        total_won = float(np.sum(payouts))
        net_profit = total_won - total_spent
        mean_return_per_ticket = net_profit / sims_to_run
        winning_tickets = int(np.sum(payouts > 0))
        win_rate = winning_tickets / sims_to_run

        is_positive_ev = analytical_ev > 0

        return {
            "ticket_cost": ticket_price,
            "jackpot_gross": jackpot,
            "tax_rate": tax_rate,
            "analytical_ev": round(analytical_ev, 4),
            "is_positive_ev": is_positive_ev,
            "roi_percentage": round((analytical_ev / ticket_price) * 100, 2),
            "ev_breakdown_by_category": ev_breakdown,
            "monte_carlo_results": {
                "simulated_draws": sims_to_run,
                "total_invested": round(total_spent, 2),
                "total_won_net": round(total_won, 2),
                "net_profit": round(net_profit, 2),
                "empirical_ev_per_ticket": round(mean_return_per_ticket, 4),
                "winning_rate_percent": round(win_rate * 100, 4),
                "hit_occurrences": {f"{k}_hits": v for k, v in hit_counts.items()}
            }
        }

    # -------------------------------------------------------------------------
    # SISTEMAS REDUCIDOS (LOTTERY WHEELS / COVERING DESIGNS)
    # -------------------------------------------------------------------------
    def generate_reduced_wheel(
        self,
        numbers: List[int],
        pick_k: int = 6,
        guarantee: int = 4
    ) -> Dict[str, Any]:
        """
        Genera un sistema reducido (Covering Design) de apuestas a partir de un subconjunto
        de números seleccionados. Utiliza un algoritmo voraz de cobertura de combinaciones (Greedy Set Cover)
        para asegurar que si los números ganadores están en el subconjunto, se garantice al menos
        una combinación con 'guarantee' aciertos utilizando el mínimo número de boletos posible.
        """
        import itertools

        clean_numbers = sorted(list(set(numbers)))
        pool_size = len(clean_numbers)

        if pool_size <= pick_k:
            return {
                "numbers_pool": clean_numbers,
                "tickets": [clean_numbers[:pick_k]],
                "total_tickets": 1,
                "guarantee": guarantee,
                "reduction_ratio": 1.0
            }

        # Subtuplas a cubrir (tuplas de tamaño 'guarantee')
        required_subsets = set(itertools.combinations(clean_numbers, guarantee))
        total_subsets_to_cover = len(required_subsets)

        # Generar universo de boletos candidatos de tamaño pick_k
        all_candidate_tickets = list(itertools.combinations(clean_numbers, pick_k))
        total_full_system = len(all_candidate_tickets)

        # Algoritmo voraz (Greedy Set Covering):
        # En cada paso, elegimos el boleto candidato que cubra la mayor cantidad de subtuplas pendientes
        covered = set()
        chosen_tickets = []

        # Precomputar qué subtuplas cubre cada boleto candidato
        ticket_to_subsets = [
            (t, set(itertools.combinations(t, guarantee)))
            for t in all_candidate_tickets
        ]

        while len(covered) < total_subsets_to_cover and ticket_to_subsets:
            # Encontrar el boleto con mayor ganancia de cobertura marginal
            best_ticket = None
            best_gain = -1
            best_idx = -1

            for idx, (cand, cand_subsets) in enumerate(ticket_to_subsets):
                gain = len(cand_subsets - covered)
                if gain > best_gain:
                    best_gain = gain
                    best_ticket = cand
                    best_idx = idx
                if gain == len(cand_subsets):
                    # Máxima ganancia posible para este boleto, selección óptima inmediata
                    break

            if best_gain <= 0 or best_ticket is None:
                break

            chosen_tickets.append(list(best_ticket))
            covered.update(ticket_to_subsets[best_idx][1])
            # Eliminar boleto ya elegido
            ticket_to_subsets.pop(best_idx)

        reduction_percentage = round((1.0 - (len(chosen_tickets) / total_full_system)) * 100, 2)

        return {
            "numbers_pool": clean_numbers,
            "pool_size": pool_size,
            "pick_k": pick_k,
            "guarantee": f"{guarantee}_if_{pick_k}",
            "full_system_tickets": total_full_system,
            "reduced_system_tickets": len(chosen_tickets),
            "coverage_percentage": round((len(covered) / total_subsets_to_cover) * 100, 2),
            "reduction_percentage": reduction_percentage,
            "tickets": chosen_tickets[:50]  # Limitar muestra a los primeros 50 para legibilidad
        }

    # -------------------------------------------------------------------------
    # CARGA DE HISTÓRICOS Y UTILIDADES
    # -------------------------------------------------------------------------
    def _load_history(self, file_path: str, raw_data: List[Any]) -> List[List[int]]:
        """Carga y sanitiza sorteos históricos desde archivo CSV/JSON o entrada de lista."""
        draws = []
        if raw_data and isinstance(raw_data, list):
            for row in raw_data:
                if isinstance(row, list):
                    clean_row = [int(x) for x in row if str(x).isdigit()]
                    if clean_row:
                        draws.append(clean_row)

        if file_path:
            p = Path(file_path)
            if not p.is_absolute():
                p = self.workspace_dir / file_path
            if p.exists() and p.is_file():
                if p.suffix.lower() == ".json":
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            if isinstance(item, list):
                                draws.append([int(x) for x in item if str(x).isdigit()])
                            elif isinstance(item, dict) and "numbers" in item:
                                draws.append([int(x) for x in item["numbers"]])
                elif p.suffix.lower() in (".csv", ".txt"):
                    with open(p, "r", encoding="utf-8") as f:
                        reader = csv.reader(f)
                        for row in reader:
                            clean_nums = []
                            for col in row:
                                try:
                                    clean_nums.append(int(col.strip()))
                                except ValueError:
                                    continue
                            if clean_nums:
                                draws.append(clean_nums)
        return draws

    def _build_text_summary(self, action: str, data: Dict[str, Any]) -> str:
        """Construye un informe textual conciso con los resultados estocásticos."""
        lines = [f"=== INFORME DE ANALÍTICA ESTOCÁSTICA Y COMBINATORIA ({action}) ==="]

        if "hypergeometric_odds" in data:
            h = data["hypergeometric_odds"]
            lines.append(f"\n[Espacio Muestral]: N={h['population_N']}, k={h['sample_k']} -> {h['total_space_size']:,} combinaciones posibles.")
            for row in h["distribution"][:3]:
                odds_str = f"1 en {row['odds_1_in']:,}" if row['odds_1_in'] else "0"
                lines.append(f"  • Acierto {row['hits']}/{h['sample_k']}: Prob = {row['probability_percent']:.6f}% ({odds_str})")

        if "historical_analysis" in data and "chi_square_test" in data["historical_analysis"]:
            ha = data["historical_analysis"]
            chi = ha["chi_square_test"]
            ent = ha["shannon_entropy"]
            lines.append(f"\n[Pruebas de Bondad de Ajuste]:")
            lines.append(f"  • Sorteos analizados: {ha['total_draws_analyzed']}")
            lines.append(f"  • Chi-cuadrado: χ² = {chi['statistic']}, p-value = {chi['p_value']} -> {chi['verdict']}")
            lines.append(f"  • Entropía de Shannon: {ent['observed_entropy_bits']} bits (Eficiencia: {ent['entropy_efficiency']*100:.2f}%)")

        if "monte_carlo_ev" in data:
            mc = data["monte_carlo_ev"]
            status = "POSITIVO (+EV)" if mc["is_positive_ev"] else "NEGATIVO (-EV)"
            lines.append(f"\n[Análisis de Valor Esperado / EV]:")
            lines.append(f"  • EV Analítico por boleto: {mc['analytical_ev']} ({status}, ROI: {mc['roi_percentage']}%)")
            lines.append(f"  • Simulación Monte Carlo ({mc['monte_carlo_results']['simulated_draws']:,} sorteos): Retorno neto = {mc['monte_carlo_results']['net_profit']}")

        if "reduced_wheel" in data:
            rw = data["reduced_wheel"]
            lines.append(f"\n[Sistema Reducido (Covering Design)]:")
            lines.append(f"  • Conjunto: {rw['pool_size']} números -> Reducido a {rw['reduced_system_tickets']} boletos (Ahorro: {rw['reduction_percentage']}%)")
            lines.append(f"  • Garantía matemática: {rw['guarantee']} ({rw['coverage_percentage']}% de cobertura)")

        return "\n".join(lines)
