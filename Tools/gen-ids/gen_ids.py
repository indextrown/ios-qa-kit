"""
gen_ids — 앱 Swift 소스를 읽어 AutoID가 런타임에 붙일 ID를 미리 계산한다.

AutoID 규칙(AutoID/AutoID.swift)과 같아야 한다:
  - VC의 뷰 프로퍼티                 : <VC>.<prop>
  - VC가 소유한 앱 커스텀 뷰의 자식   : <ViewType>.<prop>
  - 커스텀 뷰 안 커스텀 뷰의 자식     : <상위 ID>.<prop>
  - 셀 자체                           : <CellType>
  - 소유자 없는 커스텀 뷰(셀 등)의 자식: <ViewType>.<prop>
  - 앱 부모 클래스의 프로퍼티도 포함

정적 분석이라 한계가 있다: 지역 변수로 만든 뷰, 타입을 추론할 수 없는 프로퍼티는 빠진다.
그 경우 런타임 덤프(qakit dump-ui)가 정답이다. verify()로 차이를 확인한다.
Python 3.9 표준 라이브러리만 사용.
"""

import re
from pathlib import Path

EXCLUDE_DIRS = {"Pods", "Carthage", ".build", "build", "DerivedData", "SourcePackages",
                ".git", "node_modules", "fastlane", "vendor"}
EXCLUDE_SUFFIX = ("Tests", "UITests")

UIKIT_VIEWS = {
    "UIView", "UIButton", "UILabel", "UIImageView", "UITextField", "UITextView", "UIStackView",
    "UIScrollView", "UITableView", "UICollectionView", "UISwitch", "UISlider", "UISegmentedControl",
    "UIActivityIndicatorView", "UIPageControl", "UIProgressView", "UIDatePicker", "UIPickerView",
    "UIVisualEffectView", "UISearchBar", "UINavigationBar", "UIToolbar", "UITabBar", "UIControl",
    "UIStepper", "UIRefreshControl", "UITableViewCell", "UICollectionViewCell", "UICollectionViewListCell",
    "UICollectionReusableView", "UITableViewHeaderFooterView", "MKMapView", "WKWebView",
    "UIWindow", "UIInputView", "UIColorWell", "UIEventAttributionView",
}
UIKIT_VCS = {
    "UIViewController", "UITableViewController", "UICollectionViewController",
    "UINavigationController", "UITabBarController", "UIPageViewController",
    "UISplitViewController", "UIAlertController", "UIHostingController",
}
CELL_BASES = {"UITableViewCell", "UICollectionViewCell", "UICollectionViewListCell"}
VIEW_SUFFIX = re.compile(r"(View|Button|Label|Field|Control|Bar|Cell|Switch|Slider|Indicator)$")
SWIFT_KEYWORDS = {
    "default", "class", "struct", "enum", "protocol", "extension", "func", "var", "let", "import",
    "return", "if", "else", "for", "while", "switch", "case", "in", "is", "as", "self", "Self",
    "super", "init", "deinit", "subscript", "static", "public", "private", "internal", "operator",
    "where", "repeat", "do", "catch", "throw", "throws", "try", "true", "false", "nil", "Type",
    "Protocol", "break", "continue", "fallthrough", "guard", "defer", "inout", "associatedtype",
    "typealias", "rethrows", "any", "some",
}


# ─────────────────────────── 소스 정리 ───────────────────────────

def strip_comments_and_strings(src):
    """주석과 문자열 내용을 지운다 (줄 수는 유지). 중괄호 짝 맞추기를 위해."""
    out = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
        elif src.startswith("/*", i):
            depth, i = 1, i + 2
            while i < n and depth:
                if src.startswith("/*", i):
                    depth, i = depth + 1, i + 2
                elif src.startswith("*/", i):
                    depth, i = depth - 1, i + 2
                else:
                    if src[i] == "\n":
                        out.append("\n")
                    i += 1
        elif src.startswith('"""', i):
            j = src.find('"""', i + 3)
            j = n if j < 0 else j + 3
            out.append('""' + "\n" * src.count("\n", i, j))
            i = j
        elif c == '"':
            i += 1
            depth = 0  # 문자열 보간 \( ... ) 안의 괄호
            while i < n:
                if src[i] == "\\" and i + 1 < n and src[i + 1] == "(":
                    depth += 1
                    i += 2
                    continue
                if depth and src[i] == ")":
                    depth -= 1
                elif src[i] == "\\":
                    i += 1
                elif src[i] == '"' and not depth:
                    break
                elif src[i] == "\n":
                    break
                i += 1
            out.append('""')
            i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


# ─────────────────────────── 클래스/프로퍼티 추출 ───────────────────────────

CLASS_RE = re.compile(
    r"\b(?:final\s+|open\s+|public\s+|internal\s+|fileprivate\s+|private\s+|@\w+(?:\([^)]*\))?\s+)*"
    r"class\s+([A-Z]\w*)\s*(?:<[^>{]*>)?\s*(?::\s*([^{]+?))?\s*(?:where\s+[^{]+)?\{"
)
PROP_RE = re.compile(
    r"^\s*(?:@\w+(?:\([^)]*\))?\s+)*"
    r"(?:(?:private|fileprivate|internal|public|open)(?:\(set\))?\s+)*"
    r"(?:(?:weak|unowned|final|lazy|dynamic|override|nonisolated)\s+)*"
    r"(let|var)\s+(\w+)\s*(?::\s*([^=\n{]+?))?\s*(=\s*(.*))?$"
)
INIT_TYPE_RE = re.compile(r"^([A-Z][\w.]*)\s*(?:<[^>]*>)?\s*[({]")


def clean_type(t):
    if not t:
        return None
    t = t.strip().rstrip("!?").strip()
    t = re.sub(r"<.*>", "", t)
    if t.startswith("[") or t.startswith("(") or "->" in t:
        return None
    return t.split(".")[-1] if t else None


OTHER_TYPE_RE = re.compile(r"\b(?:struct|enum|protocol|typealias|actor)\s+([A-Z]\w*)")


def parse_other_types(text):
    return set(OTHER_TYPE_RE.findall(strip_comments_and_strings(text)))


def parse_classes(text):
    """{클래스명: {"super": 부모, "props": [(이름, 타입)]}}"""
    classes = {}
    clean = strip_comments_and_strings(text)
    for m in CLASS_RE.finditer(clean):
        name = m.group(1)
        inherits = m.group(2) or ""
        first = inherits.split(",")[0].strip() if inherits else None
        super_name = clean_type(first) if first and first[0].isupper() else None
        body_start = m.end()
        props = extract_props(clean, body_start)
        entry = classes.setdefault(name, {"super": super_name, "props": []})
        entry["props"] += props
    return classes


def extract_props(clean, start):
    """클래스 본문 최상위(깊이 1)의 저장 프로퍼티. 줄 단위로 읽고 줄 시작 시점의 깊이로 판단."""
    props = []
    depth = 1
    lines = clean[start:].split("\n")
    for idx, line in enumerate(lines):
        if depth <= 0:
            break
        if depth == 1:
            parsed = parse_prop_line(line)
            if parsed:
                name, typ, has_init, ends_with_brace = parsed
                stored = True
                if ends_with_brace and not has_init:
                    # var x: T { ... } → didSet/willSet이면 저장, 아니면 계산 프로퍼티
                    nxt = next((l.strip() for l in lines[idx + 1:] if l.strip()), "")
                    stored = nxt.startswith(("didSet", "willSet"))
                if stored:
                    props.append((name, typ))
        depth += line.count("{") - line.count("}")
    return props


def parse_prop_line(line):
    if re.search(r"\b(static|class)\s+(let|var)\b", line):
        return None
    if not re.search(r"\b(let|var)\s+\w+", line):
        return None
    stripped = line.rstrip()
    ends_with_brace = stripped.endswith("{")
    body = stripped[:-1] if ends_with_brace else stripped
    m = PROP_RE.match(body)
    if not m:
        return None
    _, name, annotated, init_part, init_expr = m.groups()
    typ = clean_type(annotated)
    if not typ and init_expr:
        im = INIT_TYPE_RE.match(init_expr.strip())
        if im:
            typ = clean_type(im.group(1))
    if not typ:
        return None
    if ends_with_brace and init_expr is not None:
        # let x = Foo().then {  ← 초기화 클로저, 저장 프로퍼티
        return name, typ, True, True
    return name, typ, init_part is not None, ends_with_brace


# ─────────────────────────── 타입 판별 ───────────────────────────

class Model:
    def __init__(self, classes, other_types=()):
        self.classes = classes
        self.other_types = set(other_types) - set(classes)
        self._view_props = {}

    def chain(self, name):
        seen = []
        while name and name not in seen:
            seen.append(name)
            name = self.classes.get(name, {}).get("super")
        return seen

    def is_app(self, name):
        return name in self.classes

    def is_view(self, name):
        if not name or name in self.other_types:  # 앱의 struct/enum/protocol
            return False
        for t in self.chain(name):
            if t in UIKIT_VIEWS:
                return True
            if t in UIKIT_VCS:
                return False
        last = self.chain(name)[-1]
        # 외부 라이브러리 타입: 이름으로 추정 (예: MapView)
        return not self.is_app(last) and bool(VIEW_SUFFIX.search(last))

    def is_vc(self, name):
        return any(t in UIKIT_VCS or (not self.is_app(t) and t.endswith("ViewController"))
                   for t in self.chain(name))

    def is_cell(self, name):
        # UIKit 셀 계열(UI…Cell)을 상속하면 셀. AutoID는 UITableViewCell/UICollectionViewCell 하위 전부를 셀로 본다.
        return any(t in CELL_BASES or (not self.is_app(t) and t.startswith("UI") and t.endswith("Cell"))
                   for t in self.chain(name))

    def view_props(self, name):
        """앱 클래스와 앱 부모 클래스들의 뷰 프로퍼티 (AutoID Mirror 순회와 동일)."""
        if name in self._view_props:
            return self._view_props[name]
        result, seen = [], set()
        for t in self.chain(name):
            if not self.is_app(t):
                break
            for prop, typ in self.classes[t]["props"]:
                if prop in seen:
                    continue
                if self.is_view(typ):
                    seen.add(prop)
                    result.append((clean_prop_name(prop), typ))
        self._view_props[name] = result
        return result


def clean_prop_name(name):
    return name[1:] if name.startswith("_") else name


# ─────────────────────────── ID 트리 생성 ───────────────────────────

def build(sources, exclude=()):
    classes = {}
    other_types = set()
    excl = [Path(e).resolve() for e in exclude]
    files = [f for f in iter_swift_files(sources) if not any(_inside(f, e) for e in excl)]
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        other_types |= parse_other_types(text)
        for name, entry in parse_classes(text).items():
            existing = classes.get(name)
            if existing:
                existing["props"] += entry["props"]
                existing["super"] = existing["super"] or entry["super"]
            else:
                classes[name] = entry
    model = Model(classes, other_types)

    # 다른 앱 뷰의 프로퍼티로 쓰이는 타입 = 소유자가 있는 뷰 (최상위 이름공간 불필요)
    nested_types = set()
    for name in classes:
        if model.is_view(name):
            for _, typ in model.view_props(name):
                if model.is_app(typ):
                    nested_types.add(typ)

    roots = []  # (이름공간, ID prefix, 셀 여부, 프로퍼티 소유 타입)
    vc_owned = set()
    vc_siblings = {}  # VC 소유 뷰 타입 → 같은 VC가 직접 가진 다른 뷰 타입들 (하위 경로에서 제외)
    for name in sorted(classes):
        if model.is_vc(name):
            props = list(model.view_props(name))
            chain = model.chain(name)
            if "UICollectionViewController" in chain:
                props.append(("collectionView", "UICollectionView"))
            if "UITableViewController" in chain:
                props.append(("tableView", "UITableView"))
            if props:
                roots.append(("vc", name, props))
            direct = {typ for _, typ in props}
            for _, typ in props:
                if model.is_app(typ):
                    vc_owned.add(typ)
                    vc_siblings.setdefault(typ, set()).update(direct - {typ})
    for name in sorted(classes):
        if not model.is_view(name) or not model.is_app(name):
            continue
        if name in vc_owned or model.is_cell(name) or name not in nested_types:
            roots.append(("view", name, model.view_props(name)))

    trees = []
    for kind, name, props in roots:
        node = {"name": name, "id": name if (kind == "view" and model.is_cell(name)) else None,
                "children": [], "kind": "vc" if kind == "vc" else ("cell" if model.is_cell(name) else "view")}
        for prop, typ in props:
            if kind == "vc":
                node["children"].append({"name": prop, "id": f"{name}.{prop}", "children": [], "type": typ})
            else:
                if typ in vc_siblings.get(name, ()):
                    continue  # 같은 VC가 직접 가진 뷰 → VC 이름공간에 있음 (AutoID와 동일)
                node["children"].append(subtree(model, prop, typ, f"{name}.{prop}", [name]))
        trees.append(node)
    return trees, model, len(files)


def subtree(model, prop, typ, path, stack, depth=0):
    node = {"name": prop, "id": path, "children": [], "type": typ}
    if model.is_app(typ) and typ not in stack and depth < 6:
        for child, ctyp in model.view_props(typ):
            node["children"].append(subtree(model, child, ctyp, f"{path}.{child}", stack + [typ], depth + 1))
    return node


def _inside(path, folder):
    try:
        Path(path).resolve().relative_to(folder)
        return True
    except ValueError:
        return False


def iter_swift_files(sources):
    for root in sources:
        root = Path(root)
        if root.is_file() and root.suffix == ".swift":
            yield root
            continue
        for p in root.rglob("*.swift"):
            parts = set(p.relative_to(root).parts[:-1])
            if parts & EXCLUDE_DIRS:
                continue
            if any(part.endswith(EXCLUDE_SUFFIX) for part in p.relative_to(root).parts[:-1]):
                continue
            yield p


def id_types(trees):
    types = {}

    def walk(node):
        if node.get("id"):
            types[node["id"]] = node.get("type") or node["name"]
        for c in node["children"]:
            walk(c)
    for t in trees:
        walk(t)
    return types


def all_ids(trees):
    ids = set()

    def walk(node):
        if node.get("id"):
            ids.add(node["id"])
        for c in node["children"]:
            walk(c)
    for t in trees:
        walk(t)
    return ids


# ─────────────────────────── Swift 출력 ───────────────────────────

def render_swift(trees, header_note):
    lines = [
        "// 자동 생성 파일 — 직접 수정하지 마세요. `qakit gen-ids`가 다시 만듭니다.",
        f"// {header_note}",
        "//",
        "// 사용: el(QAID.LoginView.loginButton)",
        "//       복합 컴포넌트는 .id  예) el(QAID.LoginView.emailField.id)",
        "//       셀은 .id + index/라벨  예) app.cells.matching(identifier: QAID.ShipCell.id)",
        "",
        "// swiftlint:disable all",
        "enum QAID {",
    ]
    for t in trees:
        lines += render_node(t, 1, root=True)
    lines.append("}")
    return "\n".join(lines) + "\n"


def ident(name):
    return f"`{name}`" if name in SWIFT_KEYWORDS else name


def render_node(node, level, root=False):
    pad = "    " * level
    out = []
    if not node["children"] and not root:
        out.append(f'{pad}static let {ident(node["name"])} = "{node["id"]}"')
        return out
    comment = {"vc": "  // ViewController", "cell": "  // 셀", "view": ""}.get(node.get("kind"), "")
    out.append(f'{pad}enum {ident(node["name"])} {{{comment}')
    if node.get("id"):
        out.append(f'{pad}    static let id = "{node["id"]}"')
    used = {"id"}
    for c in node["children"]:
        if c["name"] in used:  # 같은 이름 충돌 방지
            continue
        used.add(c["name"])
        out += render_node(c, level + 1)
    out.append(f"{pad}}}")
    return out


def declared_as_uikit(model, typ):
    return bool(typ) and not model.is_app(typ) and typ.startswith("UI")


def inherits_external(model, typ):
    if not typ or not model.is_app(typ):
        return False
    return not model.is_app(model.chain(typ)[-1])


# ─────────────────────────── 런타임 비교 ───────────────────────────

RULE_ID = re.compile(r"^Tab\.|\.(cell|header|footer|textField)$|\.(nav\.(left|right)|toolbar)\.\d+$")
ID_IN_DUMP = re.compile(r"#([A-Za-z_][\w.]*)")


def verify(generated, model, dump_files, types=None):
    """덤프에 나온 ID와 생성된 ID 비교. (일치, 누락, 외부)"""
    runtime = set()
    for f in dump_files:
        for m in ID_IN_DUMP.finditer(Path(f).read_text(encoding="utf-8", errors="replace")):
            runtime.add(m.group(1))
    matched, missing, external = [], [], []
    for rid in sorted(runtime):
        root = rid.split(".")[0]
        if RULE_ID.search(rid):
            external.append(rid)  # 실행 중 위치로 정해지는 규칙 ID (Tab., .cell, .nav.right.0 …)
        elif not model.is_app(root):
            external.append(rid)  # 외부 SDK 클래스 또는 에셋 이름
        elif rid in generated:
            matched.append(rid)
        elif types and inherits_external(model, types.get(rid.rsplit(".", 1)[0])):
            external.append(rid)  # 외부 SDK 부모 클래스의 프로퍼티 (소스 없음)
        elif types and declared_as_uikit(model, types.get(rid.rsplit(".", 1)[0])):
            # 예: `var x: UIView?`로 선언하고 실제로는 앱의 하위 클래스를 넣음 → 실행 중에는 안쪽 이름이 붙지만
            # 소스의 선언만으로는 알 수 없다 (정적 분석 한계)
            external.append(rid)
        else:
            missing.append(rid)
    return matched, missing, external
