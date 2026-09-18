"""Topic assignment for dynamic / in-motion WPT for robots and unmanned vehicles."""
from __future__ import annotations

SEED_SUMMARIES: dict[str, str] = {}

TOPIC_SUMMARIES: dict[str, str] = {
    "T1": "誘導・磁界共振（近接界）はロボット向け動的給電の主流方式であり、走行・飛行に伴うコイル間変動への耐性が設計の中心となる。",
    "T2": "マイクロ波・RF遠方界は移動体へのビーム給電に適するが、効率・指向・安全が制約となる。",
    "T3": "レーザー／光無線は飛行中給電に向くが、視線・天候・安全が実運用の障壁である。",
    "T4": "容量結合（CPT）は in-motion 給電の実装例があり、電極配置と高周波駆動が課題である。",
    "T5": "空中ロボット向け動的給電は in-flight・ホバリング中の位置変動が支配的である。",
    "T6": "水中・海上無人機は媒質損失とドッキング／航行中給電の両方が論点となる。",
    "T7": "地上移動ロボット・AGV は DWPT レーン・コイル切替・物流ロボット実証が中心である。",
    "T8": "走行中・航行中・飛行中の連続給電と、動的ミスアライメント／軌道制御統合が横断課題である。",
}

RESEARCH_GAPS: list[tuple[str, str, list[str]]] = [
    (
        "真の in-motion 給電の実証不足",
        "ミスアライメント耐性のみで停止充電に近い設定が多く、連続走行・航行中給電の実証が限られる。",
        [],
    ),
    (
        "プラットフォーム横断ベンチマーク",
        "AGV・UAV・AUV で同一指標（速度・ギャップ・効率）による DWPT 比較が不足。",
        [],
    ),
    (
        "方式横断比較（近接界 vs 光 vs RF）",
        "ロボット移動中給電における方式選定の定量的比較枠組みが未整備。",
        [],
    ),
]

TOPICS: dict[str, dict] = {
    "T1": {
        "name": "誘導・磁界共振（近接界）",
        "name_en": "Inductive / magnetic resonant (near-field)",
        "subtopics": {
            "T1a": "IPT・コイル結合",
            "T1b": "磁界共振・共鳴結合",
            "T1c": "補償・パワーエレクトロニクス",
        },
    },
    "T2": {
        "name": "マイクロ波・RF遠方界",
        "name_en": "Microwave / RF far-field",
        "subtopics": {
            "T2a": "マイクロ波電力伝送（MPT）",
            "T2b": "レクテナ・ビームフォーミング",
            "T2c": "SWIPT・RFハーベスティング",
        },
    },
    "T3": {
        "name": "レーザー・光無線給電",
        "name_en": "Laser / optical wireless power",
        "subtopics": {
            "T3a": "レーザーパワービーミング",
            "T3b": "光受信・光電変換",
            "T3c": "視線・安全・天候制約",
        },
    },
    "T4": {
        "name": "電界結合（CPT）",
        "name_en": "Capacitive power transfer",
        "subtopics": {
            "T4a": "電極・結合設計",
            "T4b": "高周波駆動・補償",
            "T4c": "ギャップ・位置ずれ",
        },
    },
    "T5": {
        "name": "空中ロボット（UAV）",
        "name_en": "Aerial robots (UAV/drone)",
        "subtopics": {
            "T5a": "ホバリング・飛行中給電",
            "T5b": "着陸・ドック充電",
            "T5c": "スウォーム・FANET運用",
        },
    },
    "T6": {
        "name": "水中・海上無人機",
        "name_en": "Underwater / surface vehicles",
        "subtopics": {
            "T6a": "AUV/UUV給電",
            "T6b": "ROV・ドッキング",
            "T6c": "USV・海上充電",
        },
    },
    "T7": {
        "name": "地上移動ロボット・AGV",
        "name_en": "Ground mobile robots / AGV",
        "subtopics": {
            "T7a": "モバイルロボット充電",
            "T7b": "AGV・産業搬送",
            "T7c": "ステーション・インフラ統合",
        },
    },
    "T8": {
        "name": "動的・移動中給電",
        "name_en": "Dynamic / in-motion charging",
        "subtopics": {
            "T8a": "動的ミスアライメント",
            "T8b": "軌道・位置制御との統合",
            "T8c": "走行中・航行中給電",
        },
    },
}

_IPT = (
    "inductive",
    "ipt",
    "magnetic resonance",
    "magnetic resonant",
    "resonant coupling",
    "near-field",
    "coil",
)
_MW = ("microwave", "mpt", "rectenna", "rf energy", "swipt", "far-field", "beamforming")
_LASER = ("laser", "optical wireless power", "power beaming", "photovoltaic receiver")
_CPT = ("capacitive", "cpt", "electric field coupling", "electric-field")
_UAV = ("uav", "drone", "quadrotor", "multirotor", "unmanned aerial", "aerial vehicle", "fanet")
_UW = ("auv", "uuv", "rov", "underwater", "unmanned underwater", "usv", "unmanned surface")
_GROUND = ("mobile robot", "agv", "ground robot", "wheeled robot", "legged robot", "logistics robot")
_DYN = (
    "dynamic wireless",
    "dwpt",
    "in-motion",
    "in motion",
    "while moving",
    "on-the-move",
    "moving wireless",
    "dynamic charging",
    "in-flight",
    "in flight",
    "coil switching",
    "segmented",
    "charging lane",
)


def _blob(entry: dict) -> str:
    title = (entry.get("title") or "").lower()
    abstract = (entry.get("abstract") or "").lower()[:800]
    kws = entry.get("keywords") or {}
    parts = [title, abstract]
    for ax in "PAOM":
        parts.extend(str(k).lower() for k in (kws.get(ax) or []))
    return " ".join(parts)


def assign_subtopics(entry: dict) -> list[tuple[str, str]]:
    blob = _blob(entry)
    out: list[tuple[str, str]] = []

    def hit(*words: str) -> bool:
        return any(w in blob for w in words)

    if hit(*_IPT):
        if hit("magnetic resonance", "magnetic resonant", "resonant coupling", "mcr-wpt"):
            out.append(("T1", "T1b"))
        elif hit("compensation", "inverter", "rectifier", "converter"):
            out.append(("T1", "T1c"))
        else:
            out.append(("T1", "T1a"))

    if hit(*_MW):
        if hit("rectenna", "beamforming", "beam forming"):
            out.append(("T2", "T2b"))
        elif hit("swipt", "harvest"):
            out.append(("T2", "T2c"))
        else:
            out.append(("T2", "T2a"))

    if hit(*_LASER):
        if hit("safety", "eye", "weather", "line of sight", "los"):
            out.append(("T3", "T3c"))
        elif hit("photovoltaic", "receiver", "pv "):
            out.append(("T3", "T3b"))
        else:
            out.append(("T3", "T3a"))

    if hit(*_CPT):
        if hit("gap", "misalignment", "alignment"):
            out.append(("T4", "T4c"))
        elif hit("compensation", "inverter", "high frequency", "high-frequency"):
            out.append(("T4", "T4b"))
        else:
            out.append(("T4", "T4a"))

    if hit(*_UAV):
        if hit("hover", "in-flight", "in flight", "while flying", "flight", "dynamic charging"):
            out.append(("T5", "T5a"))
        elif hit("swarm", "fanet"):
            out.append(("T5", "T5c"))
        elif hit("dock", "landing", "pad") and not hit(*_DYN):
            out.append(("T5", "T5b"))
        else:
            out.append(("T5", "T5a"))

    if hit(*_UW):
        if hit("dock", "docking") and not hit(*_DYN):
            out.append(("T6", "T6b"))
        elif hit("usv", "surface"):
            out.append(("T6", "T6c"))
        else:
            out.append(("T6", "T6a"))

    if hit(*_GROUND) or (hit("robot") and not hit(*_UAV) and not hit(*_UW)):
        if hit("agv", "industrial", "warehouse", "logistics"):
            out.append(("T7", "T7b"))
        elif hit("station", "infrastructure", "pad") and not hit(*_DYN):
            out.append(("T7", "T7c"))
        else:
            out.append(("T7", "T7a"))

    if hit(*_DYN):
        if hit("trajectory", "path", "position control", "tracking", "navigation"):
            out.append(("T8", "T8b"))
        elif hit(
            "driving",
            "cruising",
            "underway",
            "traversing",
            "in-motion",
            "while moving",
            "on-the-move",
            "dwpt",
        ):
            out.append(("T8", "T8c"))
        else:
            out.append(("T8", "T8a"))

    if not out and hit("wireless power", "wireless charging", "wpt"):
        out.append(("T1", "T1a"))

    return list(dict.fromkeys(out))
