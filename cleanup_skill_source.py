"""
清理 skill_source.md — 从 Claude Code 对话记录中提取有价值的技术内容
保留：风格约定、色值/尺寸/圆角、CSS规则、组件代码、补充说明、修正迭代记录
删除：闲聊、情绪话术、报错日志、无关命令、工具调用记录、纯确认类短句
"""
import re

INPUT_FILE = "skill_source.md"
OUTPUT_FILE = "skill_source_clean.md"


def is_noise(line):
    """判断是否为噪声行（strip 后匹配）"""
    s = line.strip()
    if not s:
        return True

    noise_starts = [
        '▐▛███▜▌', '▝▜█████▛▘', '▘▘ ▝▝',
        '✻ Conversation compacted', '✻ Crunched for', '✻ Churned for',
        '✻ Brewed for', '✻ Sautéed for', '✻ Worked for', '✻ Cooked for',
        '✻ Baked for', '✻ Cogitated for',
        '⎿  Referenced file', '⎿  Read ', 'Read 1 file', 'Read 2 file',
        'Searched for', 'Plan saved to:', '(disable recaps in',
        'transforming...', '✓ modules transformed', 'rendering chunks...',
        'computing gzip size', 'dist/', 'vite v',
        'Entered plan mode', 'Claude is now exploring', 'User approved',
        'Updated plan', '/plan to preview', '/context',
        'Entered plan mode', 'Updated plan', "User approved Claude's plan",
        '方案已通过，开始实施', '方案已写好',
        'Error editing file', 'Error: Exit code',
        'npm error', 'Could not read package.json',
        'Now let me', 'Also add', 'Let me check', 'Now add', 'Now implement',
        'Clean up unused', 'Check ', '● Explore(',
        '● Bash(', '● Read(', '● Now ', '● Also ',
        '● Let me', '● Clean up', '● Check ',
        'Explore(Explore', 'Explore(Analyze',
        '⎿  Done', '⎿  Error',
        'Context Usage', 'Memory files ·', 'Skills ·',
        'User$', 'Plugin (', 'Built-in$', 'Suggestions',
        'File reads using', 'If you are re-reading',
        'Now I see', 'I see', 'Tracing through',
    ]
    for ns in noise_starts:
        if s.startswith(ns):
            return True

    # 纯确认短句
    confirms = [
        '● 好的', '● 收到', '● 没问题', '● OK', '● ok',
        '● 构建通过', '● Build passes', '● Build passed',
        '● 修改完成', '● 修改总结', '● 改动总结', '● 所有修改完成',
        '● CSS 已完成', '● 最后确认构建通过', '● Clean up unused',
        '● 构建验证', '● 问题原因和修复',
    ]
    for c in confirms:
        if s.startswith(c):
            return True

    # 构建输出行（dist/ 开头，前面有空格）
    if re.match(r'dist/', s):
        return True
    # gzip 行
    if 'gzip' in s and ('kB' in s or 'MB' in s):
        return True

    return False


def is_valuable_line(line):
    """判断是否为有价值的技术说明行"""
    s = line.strip()

    # Claude 说明（排除工具调用）
    if s.startswith('● '):
        content = s[2:]
        tool_calls = ['Bash(', 'Read(', 'Explore(', 'Searched', 'Build passes',
                      'Now ', 'Also ', 'Let me', 'Check ', 'Clean up',
                      '好的', '收到', '构建通过', '修改完成', '修改总结',
                      '改动总结', '所有修改完成', 'CSS 已完成', '最后确认',
                      '问题原因和修复', '构建验证',
                      'Entered plan mode', 'Updated plan', 'User approved',
                      '方案已通过', '方案已写好', 'Now I see', 'I see',
                      'Tracing through']
        for tc in tool_calls:
            if content.startswith(tc):
                return False
        return True

    # 表格线
    if any(c in s for c in '│┌┐└┘├┤┬┴┼'):
        return True
    # 表格分隔行
    if s.startswith('├') or s.startswith('└') or s.startswith('┌'):
        return True

    # 编号列表
    if re.match(r'\d+\.\s+', s):
        return True

    # 项目符号列表
    if s.startswith('- ') and len(s) > 3:
        return True

    # 根因/分析说明
    if re.match(r'(根因|问题|关键发现|同时存在|问题在于|问题本质|另外)', s):
        return True

    # 方案/设计说明
    if re.match(r'(方案|设计思路|核心思路|修改清单|验证步骤|修改总结|改动总结)', s):
        return True

    return False


def extract_code_section(lines, start_idx):
    """
    从 Update/Write 操作中提取代码内容。
    返回 (end_idx, output_lines)
    """
    output = []
    header = lines[start_idx].rstrip()
    match = re.match(r'\s*●\s+(Update|Write)\((.+)\)', header)
    if not match:
        return start_idx + 1, []

    action = match.group(1)
    filepath = match.group(2).replace('\\', '/')
    output.append(f"\n### {action}: `{filepath}`\n")
    output.append("```diff\n")

    i = start_idx + 1

    # 跳过 ⎿ 行（Added X lines, removed X lines）
    while i < len(lines) and lines[i].strip().startswith('⎿'):
        i += 1

    in_diff = False
    consecutive_empty = 0

    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()

        # 遇到新的操作块
        if re.match(r'\s*●\s+(Update|Write|Bash|Read|Explore|Searched)', line):
            break
        # 遇到新的 Claude 说明（有价值的）
        if re.match(r'\s*●\s+', line) and not re.match(r'\s*●\s+\d', line):
            # 检查是否是 diff 中的行（以数字开头的）
            if not re.match(r'\s+\d+\s*[-+\s]', line):
                break

        # diff 行格式: "      行号 [-|+] 内容"
        diff_match = re.match(r'^(\s+)(\d+)\s*([-+])\s*(.*)', line)
        if diff_match:
            in_diff = True
            sign = diff_match.group(3)
            content = diff_match.group(4).rstrip()
            output.append(f"{sign} {content}\n")
            consecutive_empty = 0
            i += 1
            continue

        # 上下文行（有行号但没有 +/-）
        ctx_match = re.match(r'^(\s+)(\d+)(\s+.*)?$', line)
        if ctx_match:
            content = (ctx_match.group(3) or '').strip()
            if content:
                output.append(f"  {content}\n")
            consecutive_empty = 0
            i += 1
            continue

        # 续行（长行被拆分，10+ 空格 + sign，无行号）
        cont_match = re.match(r'^(\s{10,})([-+])(.*)', line)
        if cont_match and in_diff:
            content = cont_match.group(3).rstrip()
            if content:
                output.append(f"  {content}\n")
            i += 1
            continue

        # 空行
        if not stripped:
            consecutive_empty += 1
            if consecutive_empty <= 1:
                i += 1
                continue
            break

        # 非代码行
        break

    if in_diff:
        output.append("```\n")
    else:
        # 没有实际 diff 内容，移除开头的 ``` 标记和 ### 标题
        while output and output[-1].strip() in ('```diff', '```', ''):
            output.pop()
        # 移除空行
        while output and output[-1].strip() == '':
            output.pop()
        # 移除 ### 标题
        if output and output[-1].startswith('### '):
            output.pop()
        # 移除标题前的空行
        while output and output[-1].strip() == '':
            output.pop()

    return i, output


def process_file(input_path, output_path):
    with open(input_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    output = []
    i = 0
    section_count = 0

    # 标题
    output.append("# AgentHub Coze 风格前端重构 — 技术记录\n\n")
    output.append("> 从 Claude Code 对话记录中提取，仅保留风格约定、CSS 规则、组件代码、修正迭代记录。\n\n")

    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()

        # ---- 跳过空行 ----
        if not stripped:
            if output and output[-1].strip() != '':
                output.append('\n')
            i += 1
            continue

        # ---- 跳过噪声 ----
        if is_noise(line):
            i += 1
            continue

        # ---- 用户需求 ----
        user_match = re.match(r'^❯\s+(.+)', line)
        if user_match:
            section_count += 1
            req_text = user_match.group(1)
            # 清理图片引用和尾部标记
            req_text = re.sub(r'\[Image\s*#?\d*\]', '', req_text)
            req_text = re.sub(r'⎿\s*\[Image\s*#?\d*\]', '', req_text)
            req_text = re.sub(r'⎿$', '', req_text).strip()
            req_text = re.sub(r'^\[Image\s*#?\d*\]\s*', '', req_text)  # 开头的图片引用
            req_text = re.sub(r'\s+', ' ', req_text)  # 合并多余空格

            # 收集多行需求（直到遇到非缩进行或新的用户输入）
            j = i + 1
            while j < len(lines):
                next_line = lines[j].rstrip()
                next_stripped = next_line.strip()
                # 遇到新的段落标记停止
                if re.match(r'^❯', next_line) or re.match(r'^✻', next_line) or re.match(r'^※', next_line):
                    break
                # 遇到工具调用停止
                if re.match(r'^\s*(Searched for|Read \d+ file|⎿)', next_line):
                    j += 1
                    continue
                # 遇到噪声停止
                if is_noise(next_line):
                    j += 1
                    continue
                # 遇到代码修改停止
                if re.match(r'^\s*●\s+(Update|Write|Bash|Read|Explore)', next_line):
                    break
                # 遇到有价值的 Claude 说明停止
                if re.match(r'^\s*●\s+', next_line):
                    break
                # 收集需求内容行
                if next_stripped and not next_stripped.startswith('⎿'):
                    # 清理图片引用
                    clean = re.sub(r'\[Image\s*#?\d*\]', '', next_stripped)
                    clean = re.sub(r'⎿\s*\[Image\s*#?\d*\]', '', clean)
                    clean = clean.strip()
                    if clean:
                        req_text += ' ' + clean
                j += 1

            if req_text:
                output.append(f"\n---\n\n## {section_count}. {req_text}\n\n")
            i = j
            continue

        # ---- 回顾 ----
        recap_match = re.match(r'^※\s+recap:\s+(.+)', line)
        if recap_match:
            recap_text = recap_match.group(1)
            recap_text = re.sub(r'\(disable recaps.*$', '', recap_text).strip()
            if recap_text:
                output.append(f"> **回顾**: {recap_text}\n\n")
            i += 1
            continue

        # ---- 代码修改块 ----
        code_match = re.match(r'^\s*●\s+(Update|Write)\(', line)
        if code_match:
            end_idx, code_lines = extract_code_section(lines, i)
            if code_lines:
                output.extend(code_lines)
            i = end_idx
            continue

        # ---- 表格 ----
        if '│' in stripped or stripped.startswith('┌') or stripped.startswith('└') or stripped.startswith('├') or stripped.startswith('┤'):
            table_lines = []
            while i < len(lines):
                tl = lines[i].rstrip()
                ts = tl.strip()
                if ('│' in ts or ts.startswith('┌') or ts.startswith('└')
                    or ts.startswith('├') or ts.startswith('┤')
                    or (ts and all(c in '─' for c in ts))):
                    table_lines.append(tl)
                    i += 1
                else:
                    break
            if table_lines:
                output.append('\n')
                output.extend([l + '\n' for l in table_lines])
                output.append('\n')
            continue

        # ---- Claude 说明行 ----
        if stripped.startswith('● '):
            content = stripped[2:]
            if is_valuable_line(line):
                output.append(f"\n{content}\n\n")
            i += 1
            continue

        # ---- 根因/分析 ----
        if re.match(r'(根因|问题|关键发现|同时存在|问题在于|问题本质|另外)', stripped):
            output.append(f"\n{stripped}\n\n")
            i += 1
            continue

        # ---- 方案/设计说明 ----
        if re.match(r'(方案|设计思路|核心思路|修改清单|验证步骤)', stripped):
            output.append(f"\n**{stripped}**\n\n")
            i += 1
            continue

        # ---- 编号列表 ----
        list_match = re.match(r'(\d+)\.\s+(.+)', stripped)
        if list_match:
            output.append(f"{list_match.group(1)}. {list_match.group(2)}\n")
            i += 1
            continue

        # ---- 项目符号列表 ----
        if stripped.startswith('- ') and len(stripped) > 3:
            content = stripped[2:]
            if not re.match(r'(Searched|Read|Explore|Update|Write|Bash)', content):
                output.append(f"- {content}\n")
            i += 1
            continue

        # ---- 跳过其他 ----
        i += 1

    # 后处理：清理残留问题
    cleaned = []
    i = 0
    while i < len(output):
        line = output[i]

        # 清理所有行中的图片引用
        if '[Image' in line:
            line = re.sub(r'\[Image\s*#?\d*\]\s*', '', line)
            line = re.sub(r'⎿\s*\[Image\s*#?\d*\]\s*', '', line)

        # 跳过孤立的 ### 标题（没有后续 ```diff 块的）
        if line.startswith('### ') and i + 1 < len(output):
            next_line = output[i + 1]
            if not next_line.strip().startswith('```'):
                i += 1
                continue

        cleaned.append(line)
        i += 1

    # 清理连续空行
    final = []
    blank_count = 0
    for line in cleaned:
        if line.strip() == '':
            blank_count += 1
            if blank_count <= 2:
                final.append(line)
        else:
            blank_count = 0
            final.append(line)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.writelines(final)

    input_lines = len(lines)
    output_lines = len(final)
    reduction = (1 - output_lines / input_lines) * 100 if input_lines > 0 else 0

    print(f"输入: {input_lines} 行 ({input_path})")
    print(f"输出: {output_lines} 行 ({output_path})")
    print(f"压缩率: {reduction:.1f}%")


if __name__ == '__main__':
    process_file(INPUT_FILE, OUTPUT_FILE)
