"""デモ用シナリオの静的定義 (DB は Phase 4)。

scripted 発音採点の参照テキスト (モデル文) に加え、Phase 3 で使う
利用者役ペルソナとロールプレイ (会話採点の土台) もここに置く。
gloss_id / *_id は UI に出す Bahasa Indonesia の補助説明。
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelTurn:
    turn_no: int
    reference_text: str  # 日本語のモデル文 (発音採点の参照)
    gloss_id: str  # Bahasa の説明


@dataclass(frozen=True)
class Persona:
    """利用者役 (AI が演じる介護施設の利用者)。Claude へのプロンプトに使う。"""

    name: str  # 利用者の呼び名
    profile_ja: str  # 人物像 (日本語)
    speaking_style: str  # 話し方の指示 (初級学習者に届くやさしさ)


@dataclass(frozen=True)
class RolePlay:
    """ロールプレイ1ターン。利用者役の最初のひとことと達成ゴール。"""

    goal_ja: str  # タスク達成判定の基準 (Claude に渡す)
    opening_ja: str  # 利用者役の口火 (例: 朝の声かけへの応答)
    opening_gloss_id: str  # opening の Bahasa 補足


@dataclass(frozen=True)
class Scenario:
    key: str
    title_ja: str
    title_id: str  # Bahasa のタイトル
    model_turns: list[ModelTurn] = field(default_factory=list)
    persona: Persona | None = None
    roleplay: RolePlay | None = None


SCENARIOS: dict[str, Scenario] = {
    "kaigo_morning": Scenario(
        key="kaigo_morning",
        title_ja="朝の声かけ＋バイタルチェック",
        title_id="Sapaan pagi + cek vital (suhu & tekanan darah)",
        model_turns=[
            ModelTurn(1, "おはようございます。よく眠れましたか", "Salam pagi + tanya tidur"),
            ModelTurn(2, "体温を測りますね。腕を出してください", "Ukur suhu, minta ulurkan lengan"),
            ModelTurn(3, "血圧を測ります。少し締めますよ", "Ukur tekanan darah"),
            ModelTurn(4, "お変わりありませんか", "Tanya kabar/keadaan"),
            ModelTurn(5, "お水を飲みますか", "Tawarkan minum air"),
        ],
        persona=Persona(
            name="田中さん",
            profile_ja=(
                "あなたは介護施設で暮らす80代の利用者『田中さん』です。"
                "おだやかで少しおしゃべり好き。朝は体が少し重く、寒さを感じやすい。"
                "職員 (学習者) の声かけに、短く自然な日本語で応じてください。"
            ),
            speaking_style=(
                "初級 (A2/N4) の学習者が聞き取れるよう、やさしい語彙と短い文で話す。"
                "1ターンにつき1〜2文。難しい敬語や長文は避ける。"
            ),
        ),
        roleplay=RolePlay(
            goal_ja=(
                "学習者が利用者の発話を理解し、丁寧でその場に合った応答 (共感＋次の行動の提案) "
                "を返せたか。例: 寒さに共感し、毛布や窓の対応を申し出る。"
            ),
            opening_ja="ああ、おはよう…なんだか今日は少し寒いねえ",
            opening_gloss_id="Penghuni menyapa balik dan bilang hari ini agak dingin",
        ),
    ),
}


def get_scenario(scenario: str | None) -> Scenario | None:
    if not scenario:
        return None
    return SCENARIOS.get(scenario)


def list_turns(scenario: str) -> list[ModelTurn]:
    sc = SCENARIOS.get(scenario)
    return sc.model_turns if sc else []


def get_reference_text(scenario: str | None, turn_no: int | None) -> str | None:
    """(scenario, turn_no) からモデル文を引く。無ければ None。"""
    if not scenario or turn_no is None:
        return None
    sc = SCENARIOS.get(scenario)
    if not sc:
        return None
    for t in sc.model_turns:
        if t.turn_no == turn_no:
            return t.reference_text
    return None
