#!/usr/bin/env python3
"""把 markdown 自学材料转为带 MathJax 的 HTML（学术风格）。

设计要点：
1. 数学公式（$...$ 和 $$...$$）在 markdown 渲染前用占位符保护，渲染后恢复，
   避免 markdown 库吞掉或破坏其中字符（最常见：下划线被识别为强调）。
2. 恢复时把公式中的 < > & 转义为 HTML 实体——否则 `$s<t$` 这种写法里
   `<t` 会被浏览器 HTML 解析器误识别为标签起始符，破坏整个文档结构。
   MathJax 能正确识别 &lt; &gt; &amp; 并渲染。
3. 嵌套列表的 2 空格缩进自动补为 4 空格（python-markdown 严格要求）。
4. 列表与上文之间自动补空行（同上）。

用法：
    python3 build_html.py <input.md> <output.html> [--title "..." --header "..."]

或在 Python 代码中：
    from build_html import convert
    convert('input.md', 'output.html', title='...', header='...')

依赖：pip install markdown  （python-markdown ≥ 3.0）
"""

import argparse
import re
import sys
from pathlib import Path

import markdown


# 模板路径：默认与本脚本同目录的 html_template.html
TEMPLATE_PATH = Path(__file__).parent / 'html_template.html'


def normalize_lists(text):
    """规范化列表格式，解决 python-markdown 的两个严格要求：

    1. 列表前必须有空行，否则不识别为列表（会被并入前一段）；
    2. 嵌套列表项必须用 4 空格缩进，2 空格不识别为嵌套。

    本函数自动修复这两类问题，使用户书写 markdown 时不必拘泥于这些细节。
    """
    lines = text.split('\n')
    out = []
    for i, line in enumerate(lines):
        # 嵌套列表缩进修复：恰好 2 空格 + 列表标记 → 改为 4 空格
        m = re.match(r'^( {2})(?=[-*+] |\d+\. )', line)
        if m:
            line = '  ' + line  # 在原有 2 空格前加 2 空格

        # 顶级列表前补空行
        if i > 0:
            prev = lines[i - 1]
            top_level_list = re.match(r'^[-*+] ', line) or re.match(r'^\d+\. ', line)
            prev_is_list = re.match(r'^\s*[-*+] ', prev) or re.match(r'^\s*\d+\. ', prev)
            prev_indented = re.match(r'^\s{2,}\S', prev)
            prev_blank = prev.strip() == ''
            if top_level_list and not prev_is_list and not prev_blank and not prev_indented:
                out.append('')
        out.append(line)
    return '\n'.join(out)


def protect_math(text):
    """把所有数学公式替换为占位符，避免被 markdown 库破坏。

    支持 $$...$$ (块级) 和 $...$ (行内)。返回 (处理后文本, 公式列表)。

    特殊处理：先用占位符保护代码块（围栏与行内代码），避免代码里的 $ 被
    错误识别为数学。
    """
    formulas = []
    code_blocks = []

    def save_code(m):
        code_blocks.append(m.group(0))
        return f"\x00CODE{len(code_blocks) - 1}\x00"

    # 先保护围栏代码块 ```...```
    text = re.sub(r'```[\s\S]*?```', save_code, text)
    # 再保护行内代码 `...`
    text = re.sub(r'`[^`\n]+`', save_code, text)

    def save_block_math(m):
        formulas.append(('block', m.group(1)))
        return f"\x00MATH{len(formulas) - 1}\x00"

    def save_inline_math(m):
        formulas.append(('inline', m.group(1)))
        return f"\x00MATH{len(formulas) - 1}\x00"

    # 先块级 $$...$$（可跨行），再行内 $...$
    text = re.sub(r'\$\$([\s\S]+?)\$\$', save_block_math, text)
    # 行内：不要跨段（避免误识别没成对的 $）
    text = re.sub(r'\$([^\$\n]+?)\$', save_inline_math, text)

    # 恢复代码块占位符
    for i, cb in enumerate(code_blocks):
        text = text.replace(f"\x00CODE{i}\x00", cb)

    return text, formulas


def restore_math(html, formulas):
    """把占位符替换回 MathJax 可解析的数学公式（用 \\(...\\) 和 \\[...\\]）.

    关键：必须 HTML-escape 公式内容中的 < > &，否则浏览器 HTML 解析器
    会把 `<t` 之类当成标签开始符，破坏 DOM 结构。MathJax 能正确识别
    HTML 实体并解释为对应的 LaTeX 字符。
    """
    for i, (kind, body) in enumerate(formulas):
        placeholder = f"\x00MATH{i}\x00"
        # & 必须最先处理，否则会重复转义
        safe = body.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        if kind == 'block':
            replacement = f'\\[{safe}\\]'
        else:
            replacement = f'\\({safe}\\)'
        html = html.replace(placeholder, replacement)
    return html


def _escape(text):
    """最小化 HTML 转义，用于导航链接的标题/href 文本。"""
    return (text.replace('&', '&amp;').replace('<', '&lt;')
                .replace('>', '&gt;').replace('"', '&quot;'))


_CHAPTER_NUM_RE = re.compile(
    r'^(?:第\s*[0-9〇一二三四五六七八九十百千零两]+\s*[章节讲课]'
    r'|附录\s*[A-Za-z0-9一二三四五六七八九十]+)'
    r'\s*[:：、\.．\-—]?\s*'
)


def _strip_chapter_number(text):
    """去掉章节名开头的"第N章/第N讲"或"附录X"编号前缀，只留标题正文。

    顶部导航横幅横向空间有限，且章号在正文标题和页眉里已经出现过，
    横幅里的章节名重复标注章号只会挤占空间、无助于识别，所以去掉。
    数字与"第/章"之间允许有空格（如"第 3 章"）——不少作者习惯这样排版，
    正则里必须容忍，否则大量真实标题会匹配不上、根本不会被去掉。
    """
    if not text:
        return text
    return _CHAPTER_NUM_RE.sub('', text).strip()


def build_banner_html(title, book_title=None, index_href=None,
                       prev_href=None, prev_title=None,
                       next_href=None, next_title=None):
    """构建锁定在视口顶端的章节导航横幅（页面顶部，随滚动始终可见）。

    三栏布局，每栏两行，三栏的第一行都是小号浅色的"标签行"、第二行是
    实际内容，横向对齐成一条整齐的网格：
        ← 上一章          <全书名字>          下一章 →
        上一章章节名       <当前章节标题>       下一章章节名
    中间栏点击可返回目录（若提供 index_href）；左右两栏的章节名自动去掉
    "第N章"编号前缀。prev/next/index 三者都缺失时返回空字符串（用于
    合并版整书页面等不需要横幅的场景）；只提供部分参数时，缺失的一侧
    用不可见占位符维持左右对称，避免横幅内容跳动。
    """
    if not (prev_href or next_href or index_href):
        return ''

    if prev_href:
        prev_name = _strip_chapter_number(prev_title)
        name_html = (f'<span class="nav-side-name">{_escape(prev_name)}</span>'
                     if prev_name else '')
        prev_html = (f'<a class="nav-side nav-side-prev" href="{_escape(prev_href)}">'
                     f'<span class="nav-side-label">← 上一章</span>{name_html}</a>')
    else:
        prev_html = ('<span class="nav-side nav-side-prev nav-placeholder">'
                     '<span class="nav-side-label">← 上一章</span></span>')

    if next_href:
        next_name = _strip_chapter_number(next_title)
        name_html = (f'<span class="nav-side-name">{_escape(next_name)}</span>'
                     if next_name else '')
        next_html = (f'<a class="nav-side nav-side-next" href="{_escape(next_href)}">'
                     f'<span class="nav-side-label">下一章 →</span>{name_html}</a>')
    else:
        next_html = ('<span class="nav-side nav-side-next nav-placeholder">'
                     '<span class="nav-side-label">下一章 →</span></span>')

    book_html = (f'<span class="nav-title-book">{_escape(book_title)}</span>'
                 if book_title else '')
    title_text = _escape(title or '')
    if index_href:
        chapter_html = f'<a class="nav-title-chapter" href="{_escape(index_href)}">{title_text}</a>'
    else:
        chapter_html = f'<span class="nav-title-chapter">{title_text}</span>'

    return (f'<nav class="chapternav-banner"><div class="chapternav-banner-inner">'
            f'{prev_html}<div class="nav-title">{book_html}{chapter_html}</div>{next_html}'
            f'</div></nav>')


def build_book_toc_panel_html(entries, current_href=None):
    """构建左侧"全书目录"侧边栏（含悬浮按钮与滑出面板），整体作为一段可插入模板的 HTML。

    entries 是按阅读顺序排列的 (href, title) 列表——书里有多少章节页面，
    这里就有多少项，与"上一章/下一章"横幅呼应，让读者能跳到非相邻的
    任意章节而不必先退回目录页。当前所在的章节高亮显示且不做成链接
    （已经在这一页了，点了也没有意义）。
    未提供 entries 时返回空字符串，即整个按钮和面板都不渲染——
    没有全书目录数据的页面（如合并版整书页面）不应该出现一个点开
    是空的按钮，这与顶部导航横幅"没有上一章/下一章/目录时不渲染"
    是同一个原则。
    """
    if not entries:
        return ''
    items = []
    for href, entry_title in entries:
        text = _escape(entry_title)
        if current_href and href == current_href:
            items.append(f'<li><span class="toc-current">{text}</span></li>')
        else:
            items.append(f'<li><a href="{_escape(href)}">{text}</a></li>')
    list_html = '<ul>' + ''.join(items) + '</ul>'
    return (
        '<button id="book-toc-toggle" class="sidebar-toggle" '
        'onclick="document.getElementById(\'book-toc\').classList.toggle(\'open\')">'
        '☰<span class="toggle-label"> 全书目录</span></button>\n'
        '<nav id="book-toc" class="sidebar-panel sidebar-left">\n'
        '<h3>全书目录</h3>\n'
        f'<div id="book-toc-content">{list_html}</div>\n'
        '</nav>'
    )


def build_nav_html(extra_class, prev_href=None, prev_title=None,
                    next_href=None, next_title=None,
                    index_href=None, index_title='目录'):
    """构建单章页面底部的"上一章 · 目录 · 下一章"导航条（随文排布，不固定）。

    页面顶部的导航改用 build_banner_html（锁定在视口顶端）；本函数现在
    只用于页面底部那条不固定的收尾导航。
    三个位置都可能缺失（如全书第一章无上一章、最后一章无下一章、
    目录页/合并版不需要索引链接）——缺失时用不可见占位符保持布局对齐，
    而不是直接不渲染，避免左右两侧导航条位置随页面跳动。
    若三者都未提供，返回空字符串（不渲染导航条），用于合并版等场景。
    """
    if not (prev_href or next_href or index_href):
        return ''
    if prev_href:
        prev_html = f'<a class="nav-prev" href="{_escape(prev_href)}">← {_escape(prev_title or "上一章")}</a>'
    else:
        prev_html = '<span class="nav-prev nav-placeholder">←</span>'
    if next_href:
        next_html = f'<a class="nav-next" href="{_escape(next_href)}">{_escape(next_title or "下一章")} →</a>'
    else:
        next_html = '<span class="nav-next nav-placeholder">→</span>'
    if index_href:
        index_html = f'<a class="nav-index" href="{_escape(index_href)}">{_escape(index_title)}</a>'
    else:
        index_html = '<span class="nav-index nav-placeholder"></span>'
    return f'<nav class="chapternav {extra_class}">{prev_html}{index_html}{next_html}</nav>'


def convert(md_path, out_path, title=None, header=None, template_path=None,
            prev_href=None, prev_title=None,
            next_href=None, next_title=None,
            index_href=None, index_title='目录',
            book_title=None, toc_entries=None):
    """主转换函数。

    参数：
        md_path: 源 markdown 文件路径
        out_path: 输出 HTML 文件路径
        title: 浏览器标签页标题，默认取自第一个 H1 或文件名
        header: 页眉小字（如 "讲义 · 上册"），默认为空
        template_path: HTML 模板路径，默认用同目录下的 html_template.html
        prev_href / prev_title: 上一章的链接与标题（用于章节间跳转导航条）
        next_href / next_title: 下一章的链接与标题
        index_href / index_title: 目录页链接与显示文字，默认文字"目录"
        book_title: 全书名字，显示在顶部横幅中间标题的上方一行
        toc_entries: 全书目录（左侧侧边栏）的 (href, title) 列表，按阅读顺序
            排列；与 out_path 文件名相同的条目会被标记为"当前章节"并高亮

        prev/next/index 三者均为可选——都不传时不渲染导航条（如合并版整书页面）；
        只传其中一部分时，未传的一侧显示为不可点击的占位符以保持布局对齐
        （如第一章没有"上一章"、最后一章没有"下一章"）。
    """
    md_path = Path(md_path)
    out_path = Path(out_path)
    src = md_path.read_text(encoding='utf-8')

    # 默认 title 取第一个 H1
    if title is None:
        m = re.search(r'^#\s+(.+)$', src, re.MULTILINE)
        title = m.group(1).strip() if m else md_path.stem
    if header is None:
        header = ''

    # 预处理：规范化列表
    src = normalize_lists(src)

    # 保护数学公式
    protected, formulas = protect_math(src)

    # markdown → HTML
    md = markdown.Markdown(extensions=[
        'tables',
        'fenced_code',
        'attr_list',
        'def_list',
        'footnotes',
        'toc',
    ])
    body_html = md.convert(protected)

    # 恢复数学公式（含 HTML 实体转义）
    body_html = restore_math(body_html, formulas)

    # 套入模板
    tmpl_path = Path(template_path) if template_path else TEMPLATE_PATH
    if not tmpl_path.exists():
        raise FileNotFoundError(
            f"HTML 模板未找到：{tmpl_path}\n"
            f"请确认 html_template.html 与本脚本在同一目录。"
        )
    template = tmpl_path.read_text(encoding='utf-8')

    nav_top = build_banner_html(title, book_title=book_title, index_href=index_href,
                                 prev_href=prev_href, prev_title=prev_title,
                                 next_href=next_href, next_title=next_title)
    nav_bottom = build_nav_html('chapternav-bottom', prev_href, prev_title,
                                 next_href, next_title, index_href, index_title)
    book_toc_panel = build_book_toc_panel_html(toc_entries, current_href=out_path.name)

    page = (template
            .replace('__TITLE__', title)
            .replace('__HEADER__', header)
            .replace('__BODY__', body_html)
            .replace('__NAV_TOP__', nav_top)
            .replace('__NAV_BOTTOM__', nav_bottom)
            .replace('__BOOK_TOC_PANEL__', book_toc_panel)
            .replace('__PREV_HREF__', _escape(prev_href) if prev_href else '')
            .replace('__NEXT_HREF__', _escape(next_href) if next_href else ''))

    out_path.write_text(page, encoding='utf-8')
    print(f"  Wrote {out_path} ({len(page):,} chars, {len(formulas)} formulas)")


def main():
    p = argparse.ArgumentParser(
        description='Convert self-study material from markdown to HTML with MathJax.'
    )
    p.add_argument('input', help='Input markdown file')
    p.add_argument('output', help='Output HTML file')
    p.add_argument('--title', help='Page title (default: from H1 or filename)')
    p.add_argument('--header', default='', help='Page header (small text above main content)')
    p.add_argument('--template', help='HTML template path (default: html_template.html)')
    p.add_argument('--prev-href', help='Relative link to previous chapter (enables chapter nav bar)')
    p.add_argument('--prev-title', help='Previous chapter title shown in nav bar')
    p.add_argument('--next-href', help='Relative link to next chapter (enables chapter nav bar)')
    p.add_argument('--next-title', help='Next chapter title shown in nav bar')
    p.add_argument('--index-href', help='Relative link to the chapter index page')
    p.add_argument('--index-title', default='目录', help='Index link label (default: 目录)')
    p.add_argument('--book-title', help='Book/material name shown in the top banner, above the chapter title')
    p.add_argument('--toc-entry', action='append', default=[], metavar='HREF|TITLE',
                    help='One chapter entry for the left "whole book" sidebar, as "href|title". '
                         'Repeat once per chapter, in reading order. The entry whose href matches '
                         'this page\'s own output filename is highlighted as the current chapter.')
    args = p.parse_args()

    toc_entries = []
    for raw in args.toc_entry:
        href, _, entry_title = raw.partition('|')
        if not _:
            p.error(f'--toc-entry must be in "href|title" form, got: {raw!r}')
        toc_entries.append((href, entry_title))

    convert(args.input, args.output,
            title=args.title, header=args.header,
            template_path=args.template,
            prev_href=args.prev_href, prev_title=args.prev_title,
            next_href=args.next_href, next_title=args.next_title,
            index_href=args.index_href, index_title=args.index_title,
            book_title=args.book_title, toc_entries=toc_entries)


if __name__ == '__main__':
    main()
