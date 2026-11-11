"""表单 schema 契约与结构校验（PRD §3.2 / F1.5）。

`FormVersion.schema` 这一列 JSON 的结构由本模块**唯一**定义：
- Pydantic 模型负责「形状」——字段名、类型、必填关系
- `validate_form_schema()` 负责「语义」——跨字段的引用完整性与业务规则

设计器保存前、发布前都必须过校验；实例详情页渲染也依赖同一份结构，
所以这里是前后端共同的单一事实源（前端 `src/types/form.ts` 与之对齐）。

命名：全链路 snake_case（决策 D10）。

字段 key 的引用记法：
- 顶层字段：`amount`
- 子表列：  `items[].amount`

key 本身**不允许**含 `.` 或 `[]`，它们保留给上面的引用记法。
"""

from __future__ import annotations

import re
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, ValidationError

from app.core.constants import (
    AUTO_FILL_FIELD_TYPES,
    DEFAULT_SOURCE_FIELD_TYPES,
    DISPLAY_FIELD_TYPES,
    FORMULA_FUNCTIONS,
    FORMULA_KEYWORDS,
    OPTION_FIELD_TYPES,
    SUBTABLE_COLUMN_TYPES,
    FieldType,
    FormulaType,
    SectionStage,
)
from app.core.formula_syntax import IDENTIFIER_PATTERN, strip_string_literals
from app.schemas.conditions import ConditionGroup, referenced_fields

#: 字段/分区 key 的合法形式。禁止 `.` 与 `[]`（保留给 items[].amount 记法）
KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

MAX_SECTIONS = 50
MAX_FIELDS_PER_SECTION = 200
MAX_SUBTABLE_COLUMNS = 50


# --------------------------------------------------------------------------- 结构


class FieldOption(BaseModel):
    label: str = Field(min_length=1, max_length=128)
    #: 选项值类型放开，但同一字段内必须一致且唯一
    value: str | int | float | bool


class FieldValidators(BaseModel):
    """字段级校验规则。按控件类型取用其中的一部分。"""

    # 文本类
    min_length: int | None = Field(default=None, ge=0, le=10000)
    max_length: int | None = Field(default=None, ge=1, le=10000)
    #: 正则；后端校验时用 re.fullmatch
    regex: str | None = Field(default=None, max_length=512)
    # 数字/日期类
    min: float | None = None
    max: float | None = None
    #: 数字精度（小数位）
    precision: int | None = Field(default=None, ge=0, le=6)
    # 子表
    min_rows: int | None = Field(default=None, ge=0, le=1000)
    max_rows: int | None = Field(default=None, ge=1, le=1000)
    # 附件/图片
    max_file_count: int | None = Field(default=None, ge=1, le=50)
    max_file_size_mb: int | None = Field(default=None, ge=1, le=200)


class CascaderConfig(BaseModel):
    """级联下拉（PRD §3.2.2 增强项）。

    简化实现：由某个「父字段」的当前值决定本字段的选项集合。
    完整的任意层级级联留待后续。
    """

    parent_field: str
    #: { 父字段取值 : 选项列表 }
    options_by_parent: dict[str, list[FieldOption]] = Field(default_factory=dict)


class DisplayConfig(BaseModel):
    """展示型控件的配置（M8）。

    展示控件不绑定数据，所以只放排版/说明相关的字段；具体用哪些由 `type` 决定。
    """

    text: str | None = Field(default=None, max_length=2000)
    #: 标题级别，仅 heading 使用
    level: Literal[1, 2, 3] = 2
    #: 图片地址，仅 image_view 使用；只允许 http(s) 或站内绝对路径
    url: str | None = Field(default=None, max_length=2048)
    alt: str | None = Field(default=None, max_length=256)
    #: 受限 Markdown，仅 rich_text 使用
    markdown: str | None = Field(default=None, max_length=10000)


class FieldFormula(BaseModel):
    """公式基础子集（PRD §10 #9）：

    - `arithmetic`   数字四则，如 `amount * 0.1`、`(a + b) / 2`
    - `subtable_sum` 子表某列合计
    - `date_diff`    两个日期字段相差的天数
    - `concat`       文本拼接，如 `dept + "-" + name`
    """

    type: FormulaType
    expression: str | None = Field(default=None, max_length=512)
    subtable_key: str | None = None
    column_key: str | None = None
    start_field: str | None = None
    end_field: str | None = None
    unit: Literal["days"] = "days"


class FieldDef(BaseModel):
    """单个字段。

    类名带 Def 后缀是为了避开 pydantic 的 `Field`；不要改名。
    """

    key: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=128)
    type: FieldType
    sort: int = 0

    required: bool = False
    placeholder: str | None = Field(default=None, max_length=255)
    help: str | None = Field(default=None, max_length=512)
    default_value: Any = None

    #: 栅格宽度（24 栅格制）。null = 按列数与控件类型自动决定。M8
    span: int | None = Field(default=None, ge=1, le=24)
    #: 展示型控件配置。M8
    display: DisplayConfig | None = None

    options: list[FieldOption] = Field(default_factory=list)
    validators: FieldValidators = Field(default_factory=FieldValidators)

    #: PRD §3.2.2 的默认语义：true = 发起阶段可编辑；
    #: false = 发起阶段默认隐藏（即「某节点专属的补充字段」，F5.4）
    visible_at_start: bool = True

    formula: FieldFormula | None = None
    cascader: CascaderConfig | None = None

    #: 发起时由系统自动填充并锁定：当前发起人 / 发起人所在部门 / 流程发起时间。
    #: 仅顶层的人员、部门、日期时间控件支持；发起阶段强制只读，之后按节点权限处理。
    auto_fill: Literal["initiator", "initiator_dept", "start_time"] | None = None

    #: 发起时带入但**允许发起人修改**的默认值来源（人员 / 部门）。
    default_source: Literal["initiator", "initiator_dept"] | None = None

    #: 仅 type=subtable：行内列定义（不允许再嵌套 subtable）
    columns: list[FieldDef] = Field(default_factory=list)


class SectionDef(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=128)
    #: 阶段标签。决定该分区在审批节点上的默认可见性（机制 B）
    stage: SectionStage = SectionStage.APPLY
    sort: int = 0
    description: str | None = Field(default=None, max_length=512)
    collapsible: bool = False
    #: 分区级列数覆盖；null 表示跟随表单 layout.columns。M8
    columns: Literal[1, 2, 3, 4] | None = None
    fields: list[FieldDef] = Field(default_factory=list)


class FormLayout(BaseModel):
    label_position: Literal["top", "left"] = "top"
    columns: Literal[1, 2, 3, 4] = 2


class RuleEffect(BaseModel):
    """联动规则命中的效果。只允许收紧权限。"""

    target: str = Field(min_length=1, max_length=128)
    effect: Literal["hidden", "readonly", "required"]


class FormRule(BaseModel):
    """表单字段联动规则（M9）。"""

    id: str = Field(min_length=1, max_length=64)
    name: str | None = Field(default=None, max_length=128)
    when: ConditionGroup
    effects: list[RuleEffect] = Field(default_factory=list)
    #: 规则把字段隐藏时是否清空值（默认保留）
    clear_when_hidden: bool = False


class FormSchema(BaseModel):
    """表单版本 schema 的根。"""

    model_version: int = 1
    layout: FormLayout = Field(default_factory=FormLayout)
    sections: list[SectionDef] = Field(default_factory=list)
    rules: list[FormRule] = Field(default_factory=list)
    #: 用哪个表单字段作为实例标题（可选；不配置则用流程模板名）
    title_field: str | None = Field(default=None, max_length=64)


# --------------------------------------------------------------------------- 校验


class SchemaIssue(BaseModel):
    """一条结构问题。`path` 供设计器定位到具体字段。"""

    code: str
    message: str
    path: str = ""
    severity: Literal["error", "warning"] = "error"


def _issue(code: str, message: str, path: str, severity: Literal["error", "warning"] = "error") -> SchemaIssue:
    return SchemaIssue(code=code, message=message, path=path, severity=severity)


def _check_key(key: str, path: str, issues: list[SchemaIssue]) -> None:
    if not KEY_PATTERN.match(key):
        issues.append(
            _issue(
                "INVALID_KEY",
                f"标识 “{key}” 不合法：只能由字母、数字、下划线组成，且以字母或下划线开头"
                "（点号与方括号保留给子表列引用 i[].x，不能使用）",
                path,
            )
        )


def _check_validators(field: FieldDef, path: str, issues: list[SchemaIssue]) -> None:
    v = field.validators
    if v.min_length is not None and v.max_length is not None and v.min_length > v.max_length:
        issues.append(_issue("RANGE_INVERTED", "最小长度大于最大长度", f"{path}.validators"))
    if v.min is not None and v.max is not None and v.min > v.max:
        issues.append(_issue("RANGE_INVERTED", "最小值大于最大值", f"{path}.validators"))
    if v.min_rows is not None and v.max_rows is not None and v.min_rows > v.max_rows:
        issues.append(_issue("RANGE_INVERTED", "最小行数大于最大行数", f"{path}.validators"))

    if v.regex:
        try:
            re.compile(v.regex)
        except re.error as exc:
            issues.append(
                _issue("INVALID_REGEX", f"正则表达式无法编译：{exc}", f"{path}.validators.regex")
            )


def _check_options(field: FieldDef, path: str, issues: list[SchemaIssue]) -> None:
    if field.type in OPTION_FIELD_TYPES:
        if len(field.options) < 1:
            issues.append(_issue("OPTIONS_REQUIRED", f"“{field.label}”需要至少一个选项", path))
        elif len(field.options) < 2 and field.type in {FieldType.RADIO, FieldType.SELECT}:
            issues.append(
                _issue(
                    "OPTIONS_TOO_FEW",
                    f"“{field.label}”只有 1 个选项，单选/下拉通常需要至少 2 个",
                    path,
                    severity="warning",
                )
            )

    if field.type not in OPTION_FIELD_TYPES and field.options:
        issues.append(
            _issue(
                "OPTIONS_UNUSED",
                f"“{field.label}”是 {field.type} 类型，配置的选项不会生效",
                path,
                severity="warning",
            )
        )

    if field.options:
        seen: set[Any] = set()
        for idx, opt in enumerate(field.options):
            marker = (type(opt.value).__name__, opt.value)
            if marker in seen:
                issues.append(
                    _issue("DUPLICATE_OPTION", f"选项值 {opt.value!r} 重复", f"{path}.options[{idx}]")
                )
            seen.add(marker)
        # 类型一致性：混用字符串与数字会让下拉的选中态比较失效
        kinds = {type(o.value).__name__ for o in field.options}
        if len(kinds) > 1:
            issues.append(
                _issue(
                    "MIXED_OPTION_TYPES",
                    f"“{field.label}”的选项值类型不一致（{', '.join(sorted(kinds))}），"
                    "会导致选中态无法正确比较",
                    path,
                )
            )


def _valid_image_url(url: str) -> bool:
    url = url.strip()
    if url.startswith("/") and not url.startswith("//"):
        return True
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _check_display(field: FieldDef, path: str, issues: list[SchemaIssue]) -> bool:
    """校验展示型控件；返回 True 表示这是展示控件，调用方应跳过数据字段校验。"""
    if field.type not in DISPLAY_FIELD_TYPES:
        if field.display is not None:
            issues.append(
                _issue(
                    "DISPLAY_ON_PLAIN_FIELD",
                    f"“{field.label}”不是展示控件，配置的 display 不会生效",
                    path,
                    severity="warning",
                )
            )
        return False

    # 展示控件不绑定数据：这些配置即使写了也不会生效，提示设计者清理
    if field.required:
        issues.append(
            _issue("DISPLAY_REQUIRED", f"“{field.label}”是展示控件，不应设为必填", path, severity="warning")
        )
    if field.options:
        issues.append(
            _issue("DISPLAY_OPTIONS", f"“{field.label}”是展示控件，选项不会生效", path, severity="warning")
        )
    if field.validators.model_dump(exclude_none=True):
        issues.append(
            _issue("DISPLAY_VALIDATORS", f"“{field.label}”是展示控件，校验规则不会生效", path, severity="warning")
        )
    if field.default_value is not None:
        issues.append(
            _issue("DISPLAY_DEFAULT", f"“{field.label}”是展示控件，默认值不会写入实例数据", path, severity="warning")
        )
    if field.formula is not None:
        issues.append(
            _issue("DISPLAY_FORMULA", f"“{field.label}”是展示控件，公式不会生效", path, severity="warning")
        )
    if field.cascader is not None:
        issues.append(
            _issue("DISPLAY_CASCADER", f"“{field.label}”是展示控件，级联配置不会生效", path, severity="warning")
        )
    if field.columns:
        issues.append(
            _issue("DISPLAY_COLUMNS", f"“{field.label}”是展示控件，不能再配置子表列", path, severity="warning")
        )

    display = field.display
    if display is None:
        issues.append(_issue("DISPLAY_CONFIG_REQUIRED", f"“{field.label}”缺少展示内容配置", path))
        return True

    text = (display.text or "").strip()
    if field.type in {FieldType.HEADING, FieldType.PARAGRAPH} and not text:
        issues.append(_issue("DISPLAY_TEXT_REQUIRED", f"“{field.label}”需要填写展示文字", path))
    elif field.type is FieldType.DIVIDER and not text:
        pass  # 分割线可以没有文字
    elif field.type is FieldType.IMAGE_VIEW:
        url = (display.url or "").strip()
        if not url:
            issues.append(_issue("DISPLAY_URL_REQUIRED", f"“{field.label}”需要填写图片地址", path))
        elif not _valid_image_url(url):
            issues.append(
                _issue(
                    "DISPLAY_URL_INVALID",
                    f"“{field.label}”的图片地址只支持 http(s) 或站内绝对路径",
                    path,
                )
            )
    elif field.type is FieldType.RICH_TEXT:
        markdown = display.markdown or ""
        if not markdown.strip():
            issues.append(_issue("DISPLAY_MARKDOWN_REQUIRED", f"“{field.label}”需要填写说明内容", path))
        elif re.search(r"</?[A-Za-z][^>]*>", markdown):
            issues.append(
                _issue(
                    "DISPLAY_RAW_HTML",
                    f"“{field.label}”的说明只支持受限 Markdown，不允许直接写 HTML 标签",
                    path,
                )
            )
    return True


AUTO_FILL_LABELS = {
    "initiator": "当前发起人",
    "initiator_dept": "发起人所在部门",
    "start_time": "流程发起时间",
}

_AUTO_FILL_TYPE_HINTS = {
    "initiator": "人员选择控件",
    "initiator_dept": "部门选择控件",
    "start_time": "日期时间控件",
}


def _check_auto_fill(
    field: FieldDef,
    path: str,
    issues: list[SchemaIssue],
    *,
    in_subtable: bool,
) -> None:
    """自动填充/默认值只支持顶层字段 —— 子表行内没有「发起时」这一层语义。"""
    if field.auto_fill is None and field.default_source is None:
        return
    if field.auto_fill is not None and field.default_source is not None:
        issues.append(
            _issue(
                "AUTO_FILL_CONFLICT",
                f"“{field.label}”同时配置了自动填充和默认值，两者只能选一个",
                path,
            )
        )
        return
    if in_subtable:
        issues.append(
            _issue(
                "AUTO_FILL_SUBTABLE",
                f"子表列 “{field.label}” 不能配置发起时自动填充/默认值",
                path,
            )
        )
        return

    if field.auto_fill is not None:
        allowed = AUTO_FILL_FIELD_TYPES.get(field.auto_fill, frozenset())
        if field.type not in allowed:
            issues.append(
                _issue(
                    "AUTO_FILL_TYPE",
                    f"“{field.label}”的自动填充来源是「{AUTO_FILL_LABELS[field.auto_fill]}」，"
                    f"该控件类型不匹配：请使用{_AUTO_FILL_TYPE_HINTS[field.auto_fill]}",
                    f"{path}.auto_fill",
                )
            )

    if field.default_source is not None:
        allowed = DEFAULT_SOURCE_FIELD_TYPES.get(field.default_source, frozenset())
        if field.type not in allowed:
            issues.append(
                _issue(
                    "DEFAULT_SOURCE_TYPE",
                    f"“{field.label}”的默认值来源是「{AUTO_FILL_LABELS[field.default_source]}」，"
                    f"该控件类型不匹配：请使用{_AUTO_FILL_TYPE_HINTS[field.default_source]}",
                    f"{path}.default_source",
                )
            )


def _check_formula(
    field: FieldDef,
    path: str,
    issues: list[SchemaIssue],
    *,
    top_level_keys: dict[str, FieldType],
    subtable_by_key: dict[str, FieldDef],
) -> None:
    f = field.formula
    if field.type is FieldType.FORMULA:
        if f is None:
            issues.append(
                _issue("FORMULA_REQUIRED", f"“{field.label}”是公式字段，必须配置计算公式", path)
            )
            return
        if field.required:
            issues.append(
                _issue(
                    "FORMULA_REQUIRED_CONFLICT",
                    f"“{field.label}”由公式计算得出，不应同时设为必填",
                    path,
                    severity="warning",
                )
            )
    elif f is None:
        return
    else:
        issues.append(
            _issue(
                "FORMULA_ON_PLAIN_FIELD",
                f"“{field.label}”不是公式控件，配置的公式不会生效（请把控件类型改为「公式」）",
                path,
                severity="warning",
            )
        )

    if f.type is FormulaType.ARITHMETIC or f.type is FormulaType.CONCAT:
        if not f.expression:
            issues.append(_issue("FORMULA_INCOMPLETE", "公式缺少表达式", f"{path}.formula"))
            return
        # 先剥掉字符串字面量，否则 `name + "abc"` 里的 abc 会被当成不存在的字段
        for ident in IDENTIFIER_PATTERN.findall(strip_string_literals(f.expression)):
            # 函数名不是字段引用（ROUND(qty*price, 2) 里的 ROUND）
            if ident in FORMULA_KEYWORDS or ident.upper() in FORMULA_FUNCTIONS:
                continue
            if ident not in top_level_keys and ident not in subtable_by_key:
                issues.append(
                    _issue(
                        "FORMULA_UNKNOWN_FIELD",
                        f"公式引用了不存在的字段 “{ident}”",
                        f"{path}.formula",
                    )
                )

    elif f.type is FormulaType.SUBTABLE_SUM:
        if not f.subtable_key or not f.column_key:
            issues.append(
                _issue("FORMULA_INCOMPLETE", "子表合计需要指定子表与列", f"{path}.formula")
            )
            return
        sub = subtable_by_key.get(f.subtable_key)
        if sub is None:
            issues.append(
                _issue(
                    "FORMULA_UNKNOWN_SUBTABLE",
                    f"子表 “{f.subtable_key}” 不存在",
                    f"{path}.formula",
                )
            )
        elif not any(c.key == f.column_key for c in sub.columns):
            issues.append(
                _issue(
                    "FORMULA_UNKNOWN_COLUMN",
                    f"子表 “{f.subtable_key}” 中没有列 “{f.column_key}”",
                    f"{path}.formula",
                )
            )

    elif f.type is FormulaType.DATE_DIFF:
        if not f.start_field or not f.end_field:
            issues.append(
                _issue("FORMULA_INCOMPLETE", "日期差需要指定起止字段", f"{path}.formula")
            )
            return
        for ref in (f.start_field, f.end_field):
            if ref not in top_level_keys:
                issues.append(
                    _issue("FORMULA_UNKNOWN_FIELD", f"日期差引用了不存在的字段 “{ref}”", f"{path}.formula")
                )


def _check_column_formulas(
    subtable: FieldDef, path: str, issues: list[SchemaIssue]
) -> None:
    """子表行内公式的作用域是**本子表的列**，不是顶层字段。

    行内公式逐行计算，所以 `qty * price` 引用的是同一行的 qty / price。
    `subtable_sum` 在行内没有意义（行内没有子表），直接判错。
    """
    column_keys: dict[str, FieldType] = {}
    for col in subtable.columns:
        column_keys.setdefault(col.key, col.type)

    for cidx, col in enumerate(subtable.columns):
        if col.formula is None:
            continue
        cpath = f"{path}.columns[{cidx}]"
        if col.formula.type is FormulaType.SUBTABLE_SUM:
            issues.append(
                _issue(
                    "SUBTABLE_SUM_IN_COLUMN",
                    f"子表列 “{col.label}” 不能用「子表合计」公式（行内没有子表）",
                    cpath,
                )
            )
            continue
        _check_formula(col, cpath, issues, top_level_keys=column_keys, subtable_by_key={})


def _walk_fields(
    fields: list[FieldDef],
    path_prefix: str,
    issues: list[SchemaIssue],
    *,
    in_subtable: bool = False,
) -> dict[str, FieldType]:
    """校验一层字段（分区内或子表内），返回 {key: type}。"""
    seen: dict[str, FieldType] = {}
    for idx, field in enumerate(fields):
        path = f"{path_prefix}[{idx}]"
        _check_key(field.key, f"{path}.key", issues)

        if field.key in seen:
            issues.append(
                _issue("DUPLICATE_FIELD_KEY", f"字段标识 “{field.key}” 在本层重复", f"{path}.key")
            )
        else:
            seen[field.key] = field.type

        _check_validators(field, path, issues)
        _check_options(field, path, issues)
        _check_auto_fill(field, path, issues, in_subtable=in_subtable)

        # 展示控件不参与数据字段的级联/子表/公式校验；配置错误已在 _check_display 中收集
        if _check_display(field, path, issues):
            continue

        if field.cascader is not None:
            if field.type is not FieldType.CASCADER:
                issues.append(
                    _issue(
                        "CASCADER_ON_PLAIN_FIELD",
                        f"“{field.label}”不是级联控件",
                        path,
                        severity="warning",
                    )
                )
            elif not field.cascader.options_by_parent:
                issues.append(
                    _issue("CASCADER_EMPTY", f"“{field.label}”还没有配置级联选项", path)
                )

        if field.type is FieldType.SUBTABLE:
            if not field.columns:
                issues.append(
                    _issue("SUBTABLE_EMPTY", f"子表 “{field.label}” 还没有列", path)
                )
            if len(field.columns) > MAX_SUBTABLE_COLUMNS:
                issues.append(
                    _issue(
                        "SUBTABLE_TOO_WIDE",
                        f"子表 “{field.label}” 的列数超过上限 {MAX_SUBTABLE_COLUMNS}",
                        path,
                    )
                )
            for cidx, col in enumerate(field.columns):
                if col.type is FieldType.SUBTABLE:
                    issues.append(
                        _issue(
                            "SUBTABLE_NESTED",
                            f"子表列 “{col.label}” 不能再嵌套子表",
                            f"{path}.columns[{cidx}]",
                        )
                    )
                elif col.type not in SUBTABLE_COLUMN_TYPES:
                    issues.append(
                        _issue(
                            "SUBTABLE_COLUMN_TYPE",
                            f"控件类型 “{col.type}” 不能用在子表行内",
                            f"{path}.columns[{cidx}]",
                        )
                    )
            # 列单独校验一层（不再递归下探，已禁止嵌套子表）
            _walk_fields(field.columns, f"{path}.columns", issues, in_subtable=True)
            _check_column_formulas(field, path, issues)
        elif field.columns:
            issues.append(
                _issue(
                    "COLUMNS_ON_PLAIN_FIELD",
                    f"“{field.label}”不是子表，配置的行内列不会生效",
                    path,
                    severity="warning",
                )
            )

    return seen


MAX_RULES = 50
MAX_EFFECTS_PER_RULE = 20


def _find_cycle(graph: dict[str, set[str]]) -> list[str] | None:
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        if node in visiting:
            start = stack.index(node)
            return [*stack[start:], node]
        if node in visited:
            return None
        visiting.add(node)
        stack.append(node)
        for nxt in graph.get(node, set()):
            cycle = visit(nxt)
            if cycle is not None:
                return cycle
        stack.pop()
        visiting.discard(node)
        visited.add(node)
        return None

    for node in graph:
        cycle = visit(node)
        if cycle is not None:
            return cycle
    return None


def _check_rules(
    rules: list[FormRule],
    *,
    data_refs: dict[str, FieldType],
    target_refs: dict[str, FieldType],
    issues: list[SchemaIssue],
) -> None:
    """联动规则的引用完整性、效果约束与依赖环。"""
    if len(rules) > MAX_RULES:
        issues.append(_issue("TOO_MANY_RULES", f"联动规则数量超过上限 {MAX_RULES}", "rules"))

    seen_ids: set[str] = set()
    graph: dict[str, set[str]] = {}

    for index, rule in enumerate(rules):
        path = f"rules[{index}]"
        if rule.id in seen_ids:
            issues.append(_issue("DUPLICATE_RULE_ID", f"规则标识 “{rule.id}” 重复", f"{path}.id"))
        seen_ids.add(rule.id)

        if not rule.effects:
            issues.append(_issue("RULE_NO_EFFECT", "联动规则至少要配置一个效果", path))
        elif len(rule.effects) > MAX_EFFECTS_PER_RULE:
            issues.append(
                _issue(
                    "TOO_MANY_EFFECTS",
                    f"单条规则的效果数超过上限 {MAX_EFFECTS_PER_RULE}",
                    path,
                )
            )

        condition_refs = referenced_fields(rule.when)
        for ref in condition_refs:
            if ref not in data_refs:
                issues.append(
                    _issue(
                        "RULE_CONDITION_FIELD_MISSING",
                        f"联动规则的条件引用了不存在或不可用于条件的字段 “{ref}”",
                        f"{path}.when",
                    )
                )

        hidden_targets: set[str] = set()
        for eidx, effect in enumerate(rule.effects):
            epath = f"{path}.effects[{eidx}]"
            if effect.target not in target_refs:
                if "[]." in effect.target:
                    message = f"联动目标 “{effect.target}” 是子表列；规则目标暂只支持顶层字段"
                else:
                    message = (
                        f"联动目标 “{effect.target}” 不存在，或不是可用的数据字段"
                        "（展示控件不能作为目标）"
                    )
                issues.append(_issue("RULE_TARGET_INVALID", message, epath))
                continue

            if effect.effect == "hidden":
                hidden_targets.add(effect.target)
            if effect.effect == "required" and target_refs[effect.target] is FieldType.FORMULA:
                issues.append(
                    _issue(
                        "RULE_REQUIRED_ON_COMPUTED",
                        f"“{effect.target}”是公式字段，设为必填不会生效",
                        epath,
                        severity="warning",
                    )
                )

            # target 依赖条件里引用到的顶层字段 -> 用于检测间接环
            edges = graph.setdefault(effect.target, set())
            edges.update(ref for ref in condition_refs if ref in target_refs)

        if rule.clear_when_hidden and not hidden_targets:
            issues.append(
                _issue(
                    "RULE_CLEAR_WITHOUT_HIDDEN",
                    "开启了「隐藏时清值」，但规则没有 hidden 效果",
                    path,
                    severity="warning",
                )
            )

    cycle = _find_cycle(graph)
    if cycle is not None:
        issues.append(
            _issue(
                "RULE_CYCLE",
                "联动规则存在循环依赖：" + " → ".join(cycle),
                "rules",
            )
        )


def validate_form_schema(schema: FormSchema) -> list[SchemaIssue]:
    """结构 + 语义校验。返回全部问题（error 会阻断发布，warning 只提示）。"""
    issues: list[SchemaIssue] = []

    if not schema.sections:
        issues.append(_issue("NO_SECTION", "表单至少要有一个分区", "sections"))
        return issues

    if len(schema.sections) > MAX_SECTIONS:
        issues.append(_issue("TOO_MANY_SECTIONS", f"分区数超过上限 {MAX_SECTIONS}", "sections"))

    section_keys: set[str] = set()
    for s_idx, section in enumerate(schema.sections):
        s_path = f"sections[{s_idx}]"
        _check_key(section.key, f"{s_path}.key", issues)

        if section.key in section_keys:
            issues.append(
                _issue("DUPLICATE_SECTION_KEY", f"分区标识 “{section.key}” 重复", f"{s_path}.key")
            )
        section_keys.add(section.key)

        if len(section.fields) > MAX_FIELDS_PER_SECTION:
            issues.append(
                _issue(
                    "TOO_MANY_FIELDS",
                    f"分区 “{section.title}” 字段数超过上限 {MAX_FIELDS_PER_SECTION}",
                    s_path,
                )
            )

    # 顶层字段：跨分区的 key 必须全局唯一（实例数据以 key 为键，跨分区同 key 会互相覆盖）
    top_level: dict[str, FieldType] = {}
    top_level_dupes: list[str] = []
    for s_idx, section in enumerate(schema.sections):
        layer = _walk_fields(section.fields, f"sections[{s_idx}].fields", issues)
        for key, ftype in layer.items():
            if key in top_level:
                top_level_dupes.append(key)
            else:
                top_level[key] = ftype
    for key in dict.fromkeys(top_level_dupes):
        issues.append(
            _issue(
                "DUPLICATE_FIELD_KEY",
                f"字段标识 “{key}” 在多个分区中重复；实例数据以字段标识为键，跨分区必须唯一",
                "sections",
            )
        )

    subtable_by_key: dict[str, FieldDef] = {}
    for section in schema.sections:
        for field in section.fields:
            if field.type is FieldType.SUBTABLE:
                subtable_by_key[field.key] = field

    # 展示控件不是数据字段：公式不能引用它们
    formula_fields = {
        key: ftype for key, ftype in top_level.items() if ftype not in DISPLAY_FIELD_TYPES
    }

    # 公式引用完整性（需要先收齐所有 key，故单独一轮）
    for s_idx, section in enumerate(schema.sections):
        for f_idx, field in enumerate(section.fields):
            if field.type in DISPLAY_FIELD_TYPES:
                continue
            _check_formula(
                field,
                f"sections[{s_idx}].fields[{f_idx}]",
                issues,
                top_level_keys=formula_fields,
                subtable_by_key=subtable_by_key,
            )

    # 联动规则：条件可引用顶层字段与子表列；目标只允许顶层数据字段
    data_refs: dict[str, FieldType] = {
        key: ftype for key, ftype in top_level.items() if ftype not in DISPLAY_FIELD_TYPES
    }
    for sub in subtable_by_key.values():
        for col in sub.columns:
            if col.type not in DISPLAY_FIELD_TYPES:
                data_refs[f"{sub.key}[].{col.key}"] = col.type
    target_refs = {key: ftype for key, ftype in data_refs.items() if "[]." not in key}
    _check_rules(schema.rules, data_refs=data_refs, target_refs=target_refs, issues=issues)

    if schema.title_field:
        title_type = data_refs.get(schema.title_field)
        if title_type is None:
            issues.append(
                _issue(
                    "TITLE_FIELD_MISSING",
                    f"申请标题字段 “{schema.title_field}” 不存在，或不是可用的数据字段",
                    "title_field",
                )
            )
        elif "[]." in schema.title_field or title_type not in {
            FieldType.TEXT,
            FieldType.TEXTAREA,
        }:
            issues.append(
                _issue(
                    "TITLE_FIELD_TYPE",
                    "申请标题字段必须是顶层的单行/多行文本控件",
                    "title_field",
                )
            )

    # 机制 B 的提示：非申请区的字段若 visible_at_start=true，
    # 会绕过「补充字段默认隐藏」的设计意图
    for s_idx, section in enumerate(schema.sections):
        if section.stage is SectionStage.APPLY:
            continue
        for f_idx, field in enumerate(section.fields):
            if field.type in DISPLAY_FIELD_TYPES:
                continue
            if field.visible_at_start:
                issues.append(
                    _issue(
                        "SUPPLEMENT_VISIBLE_AT_START",
                        f"“{field.label}”位于{section.title}（非申请区），却标记为发起阶段可见；"
                        "补充字段通常应设为发起阶段隐藏，再由流程节点显式打开",
                        f"sections[{s_idx}].fields[{f_idx}]",
                        severity="warning",
                    )
                )

    return issues


def has_errors(issues: list[SchemaIssue]) -> bool:
    return any(i.severity == "error" for i in issues)


class FormSchemaError(ValueError):
    """schema JSON 连形状都不合法（不是结构问题，是类型问题）。"""

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        self.errors = errors
        super().__init__("表单结构不合法")


def parse_form_schema(raw: dict[str, Any]) -> FormSchema:
    """把存库的 JSON 解析成模型；形状不合法时抛 `FormSchemaError`。"""
    try:
        return FormSchema.model_validate(raw)
    except ValidationError as exc:
        raise FormSchemaError(exc.errors(include_url=False, include_input=False)) from exc
