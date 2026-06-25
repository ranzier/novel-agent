"""题材模板：为立项步骤按题材注入定制引导。

立项（ideation）原本只有一套通用 prompt，对玄幻之外的题材容易"用力过猛"地
硬套修炼境界。本模块为每个常见题材准备一份 GenreProfile —— 一组注入 prompt 的
自然语言片段，引导模型按题材特点生成设定与角色。

设计要点：
- profile 只影响 prompt 文本，不参与 JSON schema —— schema 始终由 ideation.py 固定，
  所以加题材、改引导都不会破坏 Bible/CharacterBook 的解析。
- 加新题材 = 在 _REGISTRY 加一条，并在前端（经 /api/genres 自动同步）即可。
- has_progression=False 的题材（悬疑/言情）没有可量化进阶维度，
  power_system 留空、角色 power_tier 留空；下游 checker 对空 tiers 会自动降级不误报。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GenreProfile:
    """单个题材的立项指导模板。各字段都是注入 prompt 的自然语言片段。"""

    key: str                                  # 规范题材名（注册主键）
    aliases: tuple[str, ...] = ()             # 别名/近义题材：修真/仙侠 → 玄幻

    has_progression: bool = True              # 是否有可量化进阶维度
    progression_label: str = ""               # 建议称谓：境界/官阶/等级/地位…
    power_system_hint: str = ""               # 对 power_system 的指导

    # 注入 bible prompt
    selling_point_guide: str = ""             # 典型卖点/爽点结构
    core_conflict_guide: str = ""             # 核心矛盾母题/模式
    worldview_guide: str = ""                 # 世界观/设定侧重
    tone_hint: str = ""                       # 典型基调与文风

    # 注入 chars prompt
    archetypes: tuple[str, ...] = ()          # 典型角色原型
    character_guide: str = ""                 # 角色塑造侧重


_XUANHUAN = GenreProfile(
    key="玄幻",
    aliases=("修真", "仙侠", "修仙", "东方玄幻", "武侠", "玄幻修真"),
    has_progression=True,
    progression_label="境界",
    power_system_hint=(
        "给出有体系感的修炼/力量阶梯，至少 6 层（如：炼气→筑基→金丹→元婴…），"
        "每层标注突破条件、瓶颈与代价，命名风格统一。"
    ),
    selling_point_guide=(
        "卖点围绕：扮猪吃虎/打脸装逼、奇遇与机缘带来的越级战力、"
        "境界稳步攀升的成长爽感、天材地宝与功法争夺。"
    ),
    core_conflict_guide=(
        "核心矛盾建议'资源/机缘争夺 + 血脉或天命纠葛'，能支撑宗门、家族、"
        "大陆乃至更高层面的层层升级冲突。"
    ),
    worldview_guide=(
        "构建灵气/大道运转的修炼世界，含宗门势力、地理大陆、天材地宝体系；"
        "金手指要新颖且受限（如特殊体质/传承/丹田异象），不能让主角无敌。"
    ),
    tone_hint="热血爽快、节奏明快，可带少年意气与江湖豪情。",
    archetypes=(
        "废柴或低起点逆袭主角（携受限金手指）",
        "红颜/道侣",
        "同门挚友或亦敌亦友的同辈天才",
        "打压主角的世家天骄/反派",
        "隐藏实力的老怪或传承之灵",
    ),
    character_guide=(
        "主角开局境界要低，留足成长空间；配角分布在不同境界与势力，"
        "形成可持续的对抗与助力网。"
    ),
)

_URBAN = GenreProfile(
    key="都市",
    aliases=("都市异能", "现代", "职场", "商战", "赘婿", "神豪", "都市生活"),
    has_progression=True,
    progression_label="地位/财富/事业",
    power_system_hint=(
        "多数都市文以事业版图、财富量级、社会地位作为进阶梯度，而非修炼境界；"
        "若是都市异能流，可给能力等级阶梯。tiers 用'阶段/层级'描述影响力跃迁。"
    ),
    selling_point_guide=(
        "卖点围绕：身份反差与隐藏大佬、打脸装逼、逆袭翻身、"
        "美食/医术/商业等专业领域的碾压式表现。"
    ),
    core_conflict_guide=(
        "核心矛盾建议'阶层跃迁 + 豪门/商战博弈'，由小到大：从个人困境到家族、"
        "商业帝国乃至行业格局的对抗。"
    ),
    worldview_guide=(
        "贴近现实的现代都市背景，设定清晰的圈层规则（商界、豪门、职场）；"
        "金手指如有须有限制（如冷却、代价、信息盲区）。"
    ),
    tone_hint="爽快解气、节奏紧凑，可带轻松幽默或都市烟火气。",
    archetypes=(
        "隐藏身份/扮猪吃虎的主角",
        "慧眼识珠的女主",
        "轻视或打压主角的反派（豪门子弟/竞争对手）",
        "提携主角的贵人或长辈",
        "提供专业视角的配角",
    ),
    character_guide=(
        "角色围绕身份与利益网络展开；主角的'反差'是核心看点。"
        "若无能力等级体系，power_tier 留空。"
    ),
)

_HISTORY = GenreProfile(
    key="历史",
    aliases=("历史穿越", "架空历史", "种田历史", "权谋", "历史军事"),
    has_progression=True,
    progression_label="官阶/权势",
    power_system_hint=(
        "以官阶品级、爵位、势力版图作为进阶梯度，晋升靠功绩、站队与权谋；"
        "tiers 描述从布衣到权倾朝野的层层台阶。"
    ),
    selling_point_guide=(
        "卖点围绕：权谋布局与翻盘、步步高升、以现代见识'降维'古代、"
        "种田发展与军事谋略。"
    ),
    core_conflict_guide=(
        "核心矛盾建议'朝堂派系斗争 + 王朝兴衰/外患'，能支撑从地方到中枢的长期权力角逐。"
    ),
    worldview_guide=(
        "构建可信的历史或架空王朝背景，含官制、势力、礼法规则；"
        "金手指（如现代知识/记忆）要受限于时代条件，不能无所不能。"
    ),
    tone_hint="沉稳大气、谋略感强，可带权谋的冷峻与家国情怀。",
    archetypes=(
        "穿越者/有现代见识的主角",
        "帝王或顶头上司",
        "朝堂政敌",
        "辅佐主角的谋士或心腹",
        "联姻或助力的红颜",
    ),
    character_guide=(
        "角色按朝堂/势力派系分布，立场与利益清晰；主角的成长是权势台阶的攀登。"
    ),
)

_SCIFI = GenreProfile(
    key="科幻",
    aliases=("星际", "赛博朋克", "机甲", "未来", "硬科幻"),
    has_progression=True,
    progression_label="科技等级/能力阶位",
    power_system_hint=(
        "以科技树、进化阶位、机甲/能力等级建模，至少 6 阶；规则强调科学逻辑自洽、"
        "能源与资源限制，避免凭空设定。"
    ),
    selling_point_guide=(
        "卖点围绕：认知颠覆与硬核设定、危机求生、科技碾压、文明探索与未知揭示。"
    ),
    core_conflict_guide=(
        "核心矛盾建议'文明存续 + 技术伦理/外敌威胁'，可由个体生存升级到种族、文明级对抗。"
    ),
    worldview_guide=(
        "构建逻辑自洽的未来/末世/星际背景，设定科技规则与边界；"
        "金手指（如系统、外星科技）须有明确的运作规则与代价。"
    ),
    tone_hint="冷硬理性、宏大或压抑，视子题材而定（星际宏大/末世压抑/赛博朋克迷离）。",
    archetypes=(
        "主角（工程师/幸存者/舰长/觉醒者）",
        "AI 或机械伙伴",
        "并肩作战的队友",
        "敌对文明/势力的代表",
        "提供技术或情报的配角",
    ),
    character_guide=(
        "角色能力与所处科技/进化阶位挂钩；主角起点要低，留出技术或进化的成长线。"
    ),
)

_SUSPENSE = GenreProfile(
    key="悬疑",
    aliases=("推理", "刑侦", "罪案", "探案", "惊悚", "悬疑推理"),
    has_progression=False,
    progression_label="",
    power_system_hint=(
        "本题材通常【没有】可量化的力量/进阶体系。power_system.name 留空、tiers 留空数组。"
        "若确有'侦查权限/组织层级'之类，放进 factions 或 rules，不要硬塞进 power_system 当'境界'升级。"
    ),
    selling_point_guide=(
        "卖点围绕：环环相扣的谜题与反转、抽丝剥茧的解谜快感、'原来如此'的信息揭露节奏、"
        "每案留尾的高悬念钩子。不靠'升级打怪'制造爽点。"
    ),
    core_conflict_guide=(
        "核心矛盾建议'真相 vs 掩盖'：连环案背后的隐藏布局者、主角与真凶的智力博弈、"
        "或体制/人性与正义的拉扯。要能支撑'单元案 + 主线大谜团'的长期结构。"
    ),
    worldview_guide=(
        "侧重现实可信的社会/机构背景（警局、事务所、特定城市/时代），设定'谜题规则'与"
        "'破案手段的边界'。金手指如有，须是受限的观察/记忆/侧写能力，不能直接给答案。"
    ),
    tone_hint="冷峻、紧张、理性克制，带悬念压迫感；可在单元间穿插轻松调剂。",
    archetypes=(
        "主角侦探/调查者（独特方法论或受限金手指）",
        "搭档/助手（提供视角与情感支点）",
        "线人或法医等专业配角",
        "贯穿主线的幕后布局者/宿敌",
        "单元案中的嫌疑人群像（可在 notes 体现）",
    ),
    character_guide=(
        "角色动机为'制造与破解谜题'服务：关键角色都应携带秘密或未解信息。"
        "主角金手指若存在须有明确代价/盲区。power_tier 一律留空（本题材无进阶体系）。"
    ),
)

_ROMANCE = GenreProfile(
    key="言情",
    aliases=("纯爱", "甜宠", "虐恋", "古言", "现言", "情感", "言情小说"),
    has_progression=False,
    progression_label="",
    power_system_hint=(
        "本题材通常【没有】可量化进阶体系。power_system.name 留空、tiers 留空数组。"
        "'关系亲密度/情感阶段'是情节维度，但不要塞进 power_system 当'境界'升级。"
    ),
    selling_point_guide=(
        "卖点围绕：情感张力与双向奔赴、甜虐节奏的拉扯、高光的心动名场面、"
        "身份/性格反差带来的化学反应。"
    ),
    core_conflict_guide=(
        "核心矛盾建议'情感阻力'：身份差距、误会与隔阂、外部势力或情敌阻挠，"
        "支撑从相遇到圆满（或虐恋）的长期情感主线。"
    ),
    worldview_guide=(
        "背景服务于情感（豪门/校园/古代后宅/娱乐圈等），设定清晰的关系网与阻力来源；"
        "不需要力量体系。"
    ),
    tone_hint="细腻、情绪饱满，甜或虐随定位而定，重氛围与心理描写。",
    archetypes=(
        "女主（成长型或独立型）",
        "男主（携反差或秘密）",
        "情敌或追求者",
        "搅局的外部势力/长辈",
        "助攻的闺蜜或挚友",
    ),
    character_guide=(
        "角色围绕情感关系网铺设，各自携带推动或阻碍感情的动机；"
        "power_tier 一律留空（本题材无进阶体系）。"
    ),
)

_GAME = GenreProfile(
    key="游戏",
    aliases=("网游", "电竞", "游戏异界", "虚拟现实", "无限流", "游戏"),
    has_progression=True,
    progression_label="等级/段位",
    power_system_hint=(
        "以等级、段位、职业天赋树建模，至少 6 阶；规则贴合游戏机制"
        "（经验、装备、技能、副本、PVP），数值成长要有内在逻辑。"
    ),
    selling_point_guide=(
        "卖点围绕：数值成长与变强反馈、副本/BOSS 攻略、神装与隐藏职业、"
        "排行榜与公会争霸的竞技爽感。"
    ),
    core_conflict_guide=(
        "核心矛盾建议'公会/势力对抗 + 现实与游戏交织'，可由个人单刷升级到团队、"
        "服务器乃至现实层面的博弈。"
    ),
    worldview_guide=(
        "构建规则清晰的游戏/虚拟世界（含数值、职业、副本体系），并交代其与现实的关系；"
        "金手指（如隐藏天赋/重生先知）须受游戏规则约束。"
    ),
    tone_hint="热血竞技、爽快明快，可带兄弟热血或电竞燃感。",
    archetypes=(
        "隐藏大佬/重生归来的主角",
        "并肩的队友/战队成员",
        "对手公会会长或敌对玩家",
        "运营方或关键 NPC 势力",
        "现实中的关联人物",
    ),
    character_guide=(
        "角色按等级/段位与阵营分布；主角起点要低或身份隐藏，留出登顶的成长线。"
    ),
)

_ZOMBIE = GenreProfile(
    key="丧尸末世",
    aliases=("末世", "末日", "丧尸", "病毒末世", "废土", "求生末世"),
    has_progression=True,
    progression_label="进化等级/实力阶位",
    power_system_hint=(
        "以幸存者的异能觉醒、进化等级或丧尸的变异阶位建模，至少 6 阶；"
        "规则强调资源（食物/弹药/安全屋）的稀缺与代价，变强要有清晰来源（晶核/病毒/觉醒）。"
    ),
    selling_point_guide=(
        "卖点围绕：末日求生的紧张刺激、囤积资源与建立据点的发展爽感、"
        "异能觉醒与越级反杀、丧尸潮压境的危机与人性考验。"
    ),
    core_conflict_guide=(
        "核心矛盾建议'生存资源争夺 + 人性与秩序崩坏'：与丧尸潮、与争抢资源的"
        "其他幸存者、与失控的势力/军方多线对抗，可由个人求生升级到据点、城市乃至重建文明。"
    ),
    worldview_guide=(
        "构建逻辑自洽的末世背景：病毒起源与扩散规则、丧尸的分级与变异、"
        "安全区/据点与废土地理；金手指（如空间/预知/异能）须有获取条件与限制。"
    ),
    tone_hint="紧张压抑、危机四伏，求生的残酷与据点发展的成就感交替。",
    archetypes=(
        "末日觉醒/重生先知的主角",
        "并肩求生的队友或红颜",
        "争夺资源的敌对幸存者势力头目",
        "失控或别有用心的军方/组织代表",
        "提供线索或庇护的关键配角",
    ),
    character_guide=(
        "角色按进化等级与所属据点/势力分布；主角起点要低，留出觉醒与变强的成长线。"
        "丧尸阵营可在 notes 体现其变异层级。"
    ),
)

_GENERIC = GenreProfile(
    key="",
    has_progression=True,                     # 保守允许进阶，但措辞软化
    progression_label="",
    power_system_hint=(
        "请根据题材自行判断是否需要可量化进阶体系：偏修炼/升级/竞技则给贴合体系与 6+ 梯度；"
        "偏情感/解谜等无量化进阶则 power_system 留空、tiers 留空数组。"
    ),
    selling_point_guide="围绕该题材读者的核心爽点组织卖点。",
    core_conflict_guide="设计能驱动长期连载的核心矛盾。",
    worldview_guide="世界观贴合题材，不要给非修真题材硬套修炼黑话。",
    tone_hint="选择契合题材的基调与文风。",
    character_guide="角色班底贴合题材；若题材无进阶体系，power_tier 留空。",
)


# 内置题材种子：首次运行写入 app_data/genres.json 后，JSON 即唯一真相源。
# 之后用户可在前端任意增删改，本元组只用于初始种子与「恢复默认」。
SEED_PROFILES: tuple[GenreProfile, ...] = (
    _XUANHUAN,
    _URBAN,
    _HISTORY,
    _SCIFI,
    _SUSPENSE,
    _ROMANCE,
    _GAME,
    _ZOMBIE,
)


def build_index(profiles: list[GenreProfile]) -> dict[str, GenreProfile]:
    """key + alias → profile。后者覆盖前者时以靠后的为准。"""
    idx: dict[str, GenreProfile] = {}
    for p in profiles:
        idx[p.key] = p
        for a in p.aliases:
            idx[a] = p
    return idx


def _match(genre: str, index: dict[str, GenreProfile]) -> GenreProfile:
    """纯匹配逻辑（不读文件）：精确 → 包含 → 回退 _GENERIC。"""
    g = (genre or "").strip()
    if not g:
        return _GENERIC
    if g in index:
        return index[g]
    for token, profile in index.items():
        if token and token in g:
            return profile
    return _GENERIC


def known_genres() -> list[str]:
    """题材名列表，按存储顺序。供 /api/genres 与前端选择器使用。"""
    from .genre_store import load_profiles

    return [p.key for p in load_profiles()]


def resolve_genre(genre: str) -> GenreProfile:
    """题材字符串 → GenreProfile；未知/空回退通用 profile。

    匹配从严到宽：
    1) 精确匹配 key 或 alias
    2) 包含匹配（输入串里含某 key/alias，如'东方玄幻爽文'命中'玄幻'）
    3) 回退 _GENERIC

    数据来自可编辑的 genre_store（首次运行以 SEED_PROFILES 种子）。
    """
    from .genre_store import current_index

    g = (genre or "").strip()
    if not g:
        return _GENERIC
    return _match(g, current_index())
