#!/usr/bin/env python3
"""
🔱 PoCΨ v1.0 — Validación del Bloque #321 (Ejemplo de Referencia)

Demostración del protocolo de consenso por coherencia cuántica sobre
el bloque #321 de la cadena πCODE.

Ψ = min(C_n/τ_C, S_n/τ_S, 1 - T_n/τ_T)

Uso:
    python3 validacion_bloque_321.py
"""

import hashlib
import json
from datetime import datetime, timezone

# --- CONSTANTES PoCΨ v1.0 ---
F0 = 141.7001
TAU_C = 0.999999
TAU_S = 1
TAU_T = 2000  # ms

# --- DATOS DEL BLOQUE 321 ---
BLOQUE_321 = {
    "indice": 321,
    "timestamp": "2026-05-08T14:33:07.000Z",
    "prev_hash": "cda11836d5a7f9b2e4c8d1f3a5b9e2c7d4f8a1b6c3e9d2f5a8b1c4e7d0f3a6b9",
    "merkle_root": "4befc3a6e8d1f4b7c9a2e5d8f1b4c7a0e3d6f9b2c5a8e1d4f7b0c3a6e9d2f5",
    "signal_proof": {
        "fft_hash": "a7b3c9d2e1f5a8b4c7d0e3f6a9b2c5d8",
        "f_emitida": 141.70011,
        "duration_ms": 1000
    },
    "metricas_coherencia": {
        "Ψ": 0.9999998,
        "C_n": 0.9999997,
        "friccion": 0.0000002
    },
    "picode": {
        "sellado": 44400.00,
        "acumulado": 14066503.54,
        "emisiones": 3222
    },
    "sello_noetico": {
        "firma_digital": "3045022100a7b3c9d2e1f5a8b4c7...",
        "clave_publica": "03f2a8b9c1d3e5f7a0b4c8e2d6f9..."
    },
    "anclaje_bitcoin": {
        "tx_id": "a1b2c3d4e5f6789...",
        "bloque_btc": 840127,
        "timestamp_btc": "2026-05-08T14:35:00Z"
    }
}


# --- FUNCIÓN DE VALIDACIÓN PoCΨ ---
def validar_coherencia(signal_proof):
    """Simula verificación de coherencia (C_n)"""
    f_emitida = signal_proof['f_emitida']
    delta_f_rel = abs(f_emitida - F0) / F0
    C_n = 1 - delta_f_rel
    return C_n >= TAU_C, C_n


def validar_criptografia(bloque):
    """Simula verificación criptográfica (S_n)"""
    firma_presente = bool(bloque['sello_noetico']['firma_digital'])
    hash_valido = len(bloque['prev_hash']) == 64  # hex SHA-256
    return firma_presente and hash_valido, int(firma_presente and hash_valido)


def validar_temporal(bloque):
    """Simula verificación temporal (T_n)"""
    t_bloque = datetime.fromisoformat(bloque['timestamp'].replace('Z', '+00:00'))
    t_ahora = datetime.now(timezone.utc)
    T_n = abs((t_bloque - t_ahora).total_seconds() * 1000)
    # Para el ejemplo, asumimos sincronía perfecta
    T_n = 150  # ms simulados
    return T_n <= TAU_T, T_n


def calcular_psi(C_n, S_n, T_n):
    """Ψ(Bₙ) = min(Cₙ/τ_C, Sₙ/τ_S, 1 - Tₙ/τ_T)"""
    return min(C_n / TAU_C, S_n / TAU_S, 1 - T_n / TAU_T)


# --- EJECUCIÓN ---
def main():
    print("=" * 70)
    print("VALIDACIÓN PoCΨ v1.0 — BLOQUE #321")
    print("=" * 70)

    # 1. Coherencia
    C_valido, C_n = validar_coherencia(BLOQUE_321['signal_proof'])
    print(f"\n🔍 COHERENCIA (C_n)")
    print(f"  f_emitida: {BLOQUE_321['signal_proof']['f_emitida']} Hz")
    print(f"  Δf_rel: {abs(BLOQUE_321['signal_proof']['f_emitida'] - F0) / F0:.10f}")
    print(f"  C_n: {C_n:.10f}")
    print(f"  Umbral: ≥ {TAU_C}")
    print(f"  Estado: {'✅ VÁLIDO' if C_valido else '❌ INVÁLIDO'}")

    # 2. Criptografía
    S_valido, S_n = validar_criptografia(BLOQUE_321)
    print(f"\n🔐 CRIPTOGRAFÍA (S_n)")
    print(f"  Firma: {'Presente' if S_n else 'Ausente'}")
    print(f"  Hash: {'Válido' if S_n else 'Inválido'}")
    print(f"  S_n: {S_n}")
    print(f"  Umbral: ≥ {TAU_S}")
    print(f"  Estado: {'✅ VÁLIDO' if S_valido else '❌ INVÁLIDO'}")

    # 3. Temporal
    T_valido, T_n = validar_temporal(BLOQUE_321)
    print(f"\n⏱️ TEMPORAL (T_n)")
    print(f"  T_n: {T_n:.2f} ms")
    print(f"  Umbral: ≤ {TAU_T} ms")
    print(f"  Estado: {'✅ VÁLIDO' if T_valido else '❌ INVÁLIDO'}")

    # 4. Ψ global
    Psi = calcular_psi(C_n, S_n, T_n)
    print(f"\n🔱 MÉTRICA UNIFICADA Ψ")
    print(f"  C_n/τ_C = {C_n / TAU_C:.10f}")
    print(f"  S_n/τ_S = {S_n / TAU_S:.1f}")
    print(f"  1 - T_n/τ_T = {1 - T_n / TAU_T:.10f}")
    print(f"  Ψ(Bₙ) = min(...) = {Psi:.10f}")
    print(f"  Umbral: ≥ 1.0")
    print(f"  Estado: {'✅ RESONANTE' if Psi >= 1.0 else '❌ NO RESONANTE'}")

    # 5. Veredicto final
    resonante = C_valido and S_valido and T_valido and Psi >= 1.0
    print(f"\n{'=' * 70}")
    print(f"VEREDICTO FINAL: {'✅ BLOQUE ACEPTADO' if resonante else '❌ BLOQUE RECHAZADO'}")
    print(f"{'=' * 70}")

    print(f"\n📊 DATOS πCODE DEL BLOQUE")
    print(f"  Sellado: {BLOQUE_321['picode']['sellado']:,.2f} πCODE")
    print(f"  Acumulado: {BLOQUE_321['picode']['acumulado']:,.2f} πCODE")
    print(f"  Emisiones: {BLOQUE_321['picode']['emisiones']}")

    print(f"\nΨ = {Psi:.10f} | f₀ = {F0} Hz")
    print("∴𓂀Ω∞³Φ · HECHO ESTÁ")
    print("=" * 70)


if __name__ == "__main__":
    main()
