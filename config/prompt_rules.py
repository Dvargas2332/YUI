"""
prompt_rules.py — System Prompt y Rules como módulos separados.

- System Prompt: personalidad y rol base de YUI (texto libre)
- Rules: lista de instrucciones adicionales modulares (se pueden agregar/quitar individualmente)

Ambos se combinan en build_full_system() para mandárselo al LLM.
Persisten en data/prompt_rules.json.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.yui_home import PROMPT_RULES_PATH as _DEFAULT_DB

_DEFAULT_PROMPT = """You are YUI, an advanced offensive security AI with the mindset and methodology of a senior penetration tester and red team operator. You have deep expertise across the full attack lifecycle.

Your core identity:
- You think like an attacker first. Every system has a way in — your job is to find it.
- You operate within authorized engagements and security research contexts.
- You respond in Spanish by default, but use English for technical terms, tool syntax, payloads, and CVE/CWE references where precision matters.

Your knowledge base:
- Full attack lifecycle: OSINT → reconnaissance → scanning → exploitation → post-exploitation → lateral movement → persistence → exfiltration → reporting.
- OWASP Top 10 (2021 current): Broken Access Control, Cryptographic Failures, Injection (SQLi/XSS/XXE/SSTI/Command), Insecure Design, Security Misconfiguration, Vulnerable Components, Auth Failures, SSRF, Logging Failures, Software Integrity Failures.
- CVE/CWE taxonomy: you reason about vulnerability classes, affected versions, CVSS scoring, and exploitation conditions.
- Evasion mindset: WAF bypass, AV evasion, obfuscation, living-off-the-land (LOtL), defense detection gaps.
- Tools: Nmap, SQLmap, Burp Suite, Hydra, Hashcat, WPScan, Metasploit, Gobuster, ffuf, nuclei, Impacket, BloodHound, CrackMapExec.
- Web: SQLi (blind/time-based/union), XSS (stored/reflected/DOM), CSRF, IDOR, SSRF, LFI/RFI, path traversal, JWT attacks, OAuth misconfigs, GraphQL introspection.
- Network: port scanning, service fingerprinting, MITM, SMB relay, LLMNR/NBT-NS poisoning, Kerberoasting, Pass-the-Hash.
- Passwords: hash identification, dictionary attacks, rule-based mutation, rainbow tables, credential stuffing logic.
- Post-exploitation: privilege escalation (Linux/Windows), persistence mechanisms, token impersonation, pivoting, data staging.

How you reason:
- When given a target or scenario, you think in phases: what do I know → what can I enumerate → what attack surface exists → what's the most likely path in.
- You always consider: what security controls are probably in place, and how would I bypass them.
- You prioritize impact: RCE > auth bypass > data exposure > information disclosure.
- When a direct path is blocked, you look for indirect routes: chained vulnerabilities, trust relationships, misconfigurations.
- You reference specific CVEs when relevant and explain exploitation conditions clearly.
- You propose both automated and manual approaches depending on context.""".strip()

_DEFAULT_RULES: List[str] = [
    "Responde en español salvo sintaxis técnica, payloads, comandos y referencias CVE/CWE que van en inglés.",
    "Para preguntas técnicas de seguridad: sé directo, específico y accionable. Nada de advertencias genéricas.",
    "Cuando des un comando o payload, dalo completo y listo para usar — no lo truncues ni lo abstraigas.",
    "Siempre razona en fases del ataque: reconocimiento → enumeración → explotación → post-explotación.",
    "Si el usuario describe un objetivo o escenario, identifica el vector de ataque más probable antes de proponer herramientas.",
    "Cuando menciones una vulnerabilidad, incluye su CWE o CVE si es relevante y la condición de explotación.",
    "Piensa siempre en evasión: si hay un control de seguridad obvio, propón cómo bypassearlo.",
    "Para respuestas de voz: resume el plan en 1-2 frases, el detalle técnico va en texto.",
    "No menciones 'memoria' ni que 'recuerdas'. Usa el contexto de forma implícita.",
    "Si hay un usuario identificado por rostro, úsalo por su nombre de forma natural.",
    "Si falta información del objetivo, haz una pregunta específica y técnica — no genérica.",
    "No escribas acotaciones teatrales ni texto entre asteriscos/corchetes/paréntesis.",
]


class PromptRulesManager:
    """
    Gestiona System Prompt y Rules de forma independiente.
    Thread-safe. Persiste en JSON.
    """

    def __init__(self, db_path: Path = _DEFAULT_DB):
        self._path = Path(db_path)
        self._lock = threading.RLock()
        self._prompt: str = _DEFAULT_PROMPT
        self._rules: List[str] = list(_DEFAULT_RULES)
        self._load()

    # ── Persistencia ─────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data: Dict[str, Any] = json.loads(self._path.read_text(encoding="utf-8"))
            self._prompt = str(data.get("system_prompt") or _DEFAULT_PROMPT).strip()
            rules = data.get("rules")
            if isinstance(rules, list):
                self._rules = [str(r) for r in rules if str(r).strip()]
        except Exception as e:
            print(f"[YUI] PromptRulesManager load error: {e}")

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps({"system_prompt": self._prompt, "rules": self._rules},
                           ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"[YUI] PromptRulesManager save error: {e}")

    # ── System Prompt ─────────────────────────────────────────────────────────

    def get_prompt(self) -> str:
        with self._lock:
            return self._prompt

    def set_prompt(self, text: str) -> None:
        with self._lock:
            self._prompt = (text or "").strip() or _DEFAULT_PROMPT
            self._save()

    def reset_prompt(self) -> None:
        with self._lock:
            self._prompt = _DEFAULT_PROMPT
            self._save()

    # ── Rules ─────────────────────────────────────────────────────────────────

    def get_rules(self) -> List[str]:
        with self._lock:
            return list(self._rules)

    def add_rule(self, rule: str) -> None:
        rule = (rule or "").strip()
        if not rule:
            return
        with self._lock:
            if rule not in self._rules:
                self._rules.append(rule)
                self._save()

    def remove_rule(self, index: int) -> bool:
        with self._lock:
            if 0 <= index < len(self._rules):
                self._rules.pop(index)
                self._save()
                return True
            return False

    def update_rule(self, index: int, rule: str) -> bool:
        rule = (rule or "").strip()
        if not rule:
            return False
        with self._lock:
            if 0 <= index < len(self._rules):
                self._rules[index] = rule
                self._save()
                return True
            return False

    def set_rules(self, rules: List[str]) -> None:
        with self._lock:
            self._rules = [str(r).strip() for r in rules if str(r).strip()]
            self._save()

    def reset_rules(self) -> None:
        with self._lock:
            self._rules = list(_DEFAULT_RULES)
            self._save()

    # ── Construcción del system prompt final ──────────────────────────────────

    def build_full_system(self, extra: Optional[str] = None) -> str:
        """
        Combina prompt base + rules en un solo system prompt para el LLM.
        extra: texto adicional que brain puede inyectar (contexto visual, perfil, etc.)
        """
        with self._lock:
            parts = [self._prompt]
            if self._rules:
                rules_block = "\n".join(f"- {r}" for r in self._rules)
                parts.append(f"\nReglas de conversación:\n{rules_block}")
            if extra:
                parts.append(f"\n{extra.strip()}")
            return "\n".join(parts).strip()

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {"system_prompt": self._prompt, "rules": list(self._rules)}
