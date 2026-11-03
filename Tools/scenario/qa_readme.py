"""
qa_readme — 작업공간(QA 폴더)의 README.md를 파일만 보고 자동으로 만든다 (AI 없음).

- 시나리오(scenarios/*.qa.yml): name, 맨 위 주석(설명), reset 여부, 쓰는 공통 단계, 마지막 실행 결과
- 공통 단계(steps/*.qa.yml): 맨 위 주석(설명), 쓰는 시나리오
- Swift 테스트(Runner/UITests/Flows/*Tests.swift): 클래스·테스트 함수와 /// 주석, 마지막 실행 결과
자동 부분은 <!-- qakit:auto:start --> ~ <!-- qakit:auto:end --> 사이에만 쓰고, 그 밖의 글은 보존한다.
"""

import json
import re
from pathlib import Path

import scenario_tools

START = "<!-- qakit:auto:start -->"
END = "<!-- qakit:auto:end -->"


def _top_comments(text, limit=2):
    """첫 번째 주석 묶음의 앞 줄들 (설명). 설명은 맨 위 주석 1~2줄로 쓰는 것이 규칙."""
    out, started = [], False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("steps:"):
            break
        if s.startswith("#"):
            started = True
            body = s.lstrip("#").strip()
            if body:
                out.append(body)
        elif started:
            break
    return out[:limit]


def _uses(steps, out=None):
    out = [] if out is None else out
    for st in steps or []:
        if isinstance(st, dict):
            if "use" in st and st["use"] not in out:
                out.append(st["use"])
            for k in ("then", "else", "steps"):
                _uses(st.get(k), out)
            if isinstance(st.get("repeat"), dict):
                _uses(st["repeat"].get("steps"), out)
    return out


def _last_results(root):
    f = root / "history.jsonl"
    last = {}
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            last[r.get("test", "")] = r
    return last


def _result_cell(r):
    if not r:
        return "-"
    mark = {"Passed": "✅", "Failed": "❌", "Skipped": "⏭"}.get(r.get("result"), "•")
    return f"{mark} {r.get('at', '')[:16].replace('T', ' ')} ({r.get('seconds', 0)}초)"


def _swift_tests(root):
    flows = root / "Runner" / "UITests" / "Flows"
    out = []
    if not flows.exists():
        return out
    for f in sorted(flows.glob("*Tests.swift")):
        text = f.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        cls, cls_doc = None, ""
        file_doc = next((l.strip().lstrip("/").strip() for l in lines
                         if l.strip().startswith("//") and not l.strip().startswith("///")), "")
        for i, line in enumerate(lines):
            m = re.match(r"\s*(?:final\s+)?class\s+(\w+)\s*:", line)
            if m and cls is None:
                cls = m.group(1)
                cls_doc = _doc_above(lines, i, first_only=True) or file_doc
            m = re.match(r"\s*func\s+(test\w*)\s*\(", line)
            if m and cls:
                out.append((cls, m.group(1), _doc_above(lines, i) or cls_doc, f.name))
    return out


def _doc_above(lines, i, first_only=False):
    doc = []
    j = i - 1
    while j >= 0 and lines[j].strip().startswith("///"):
        doc.insert(0, lines[j].strip()[3:].strip())
        j -= 1
    doc = [d for d in doc if d]
    return (doc[0] if doc else "") if first_only else " ".join(doc)


def _esc(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def render(root):
    last = _last_results(root)
    scen_rows, step_users = [], {}
    for f in sorted((root / "scenarios").glob("*.qa.yml")):
        text = f.read_text(encoding="utf-8")
        try:
            data = scenario_tools.parse_yaml(text)
        except scenario_tools.YamlError:
            data = {}
        stem = f.name.replace(".qa.yml", "")
        uses = _uses(data.get("steps"))
        for u in uses:
            step_users.setdefault(u, []).append(stem)
        desc = " ".join(_top_comments(text))
        scen_rows.append((stem, data.get("name", ""), desc, data.get("reset") is True, uses, last.get(stem)))

    lines = [START, "", "## QA 목록 (자동 생성)", "",
             "> `qakit`이 파일을 보고 만든다 (run·test·check·save·restore 때 갱신, 수동: `qakit readme`). 이 표시 사이는 직접 고치지 않는다.", ""]

    lines += ["### 시나리오 파일 — `qakit run <이름>`", ""]
    if scen_rows:
        lines += ["| 이름 | 무엇을 확인하나 | 앱 초기화 | 쓰는 공통 단계 | 마지막 실행 |", "|---|---|---|---|---|"]
        for stem, name, desc, reset, uses, r in scen_rows:
            what = f"**{_esc(name)}**" + (f"<br>{_esc(desc)}" if desc else "")
            lines.append(f"| `{stem}` | {what} | {'예 ⚠️' if reset else '아니오'} | "
                         f"{', '.join(f'`{u}`' for u in uses) or '-'} | {_result_cell(r)} |")
        if any(r[3] for r in scen_rows):
            lines += ["", "⚠️ 앱 초기화 시나리오는 실행 전에 앱을 재설치하고 키체인을 지운다 (로그아웃 상태부터 시작)."]
    else:
        lines.append("(없음)")
    lines.append("")

    lines += ["### 공통 단계 — 시나리오에서 `- use: <이름>`", ""]
    step_files = sorted((root / "steps").glob("*.qa.yml"))
    if step_files:
        lines += ["| 이름 | 하는 일 | 쓰는 시나리오 |", "|---|---|---|"]
        for f in step_files:
            stem = f.name.replace(".qa.yml", "")
            desc = " ".join(_top_comments(f.read_text(encoding="utf-8")))
            users = step_users.get(stem, [])
            lines.append(f"| `{stem}` | {_esc(desc) or '-'} | {', '.join(f'`{u}`' for u in users) or '-'} |")
    else:
        lines.append("(없음)")
    lines.append("")

    tests = _swift_tests(root)
    lines += ["### Swift 테스트 — `qakit test <클래스>[/<테스트>]`", ""]
    if tests:
        lines += ["| 테스트 | 무엇을 확인하나 | 파일 | 마지막 실행 |", "|---|---|---|---|"]
        for cls, fn, doc, fname in tests:
            r = last.get(f"{cls}/{fn}()")
            lines.append(f"| `{cls}/{fn}` | {_esc(doc) or '-'} | `{fname}` | {_result_cell(r)} |")
    else:
        lines.append("(없음)")
    lines += ["", END]
    return "\n".join(lines)


def write(root, name, app_line=""):
    root = Path(root)
    path = root / "README.md"
    auto = render(root)
    if path.exists():
        text = path.read_text(encoding="utf-8")
        if START in text and END in text:
            new = text[: text.index(START)] + auto + text[text.index(END) + len(END):]
        else:
            new = text.rstrip() + "\n\n" + auto + "\n"
    else:
        new = f"""# {name} QA

이 폴더는 ios-qa-kit QA 작업공간이다. {app_line}

- 실행: `qakit run <시나리오>` / `qakit test` / 기록 `qakit history`
- 새 QA 만들기: AI에게 `/ios-qa-kit <시나리오 설명>` (만든 뒤 `qakit save`)
- 앱 특이사항: `NOTES.md` · 복구: `qakit restore`

{auto}
"""
    if not path.exists() or path.read_text(encoding="utf-8") != new:
        path.write_text(new, encoding="utf-8")
        return True
    return False
