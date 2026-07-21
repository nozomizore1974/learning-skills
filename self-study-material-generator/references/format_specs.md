# 格式技术规范

## Markdown

- 使用标准 CommonMark + GFM 扩展（表格、删除线、代码块语言标注）；
- 数学公式：行内 `$...$`、块级 `$$...$$`；
- 章节标题层级：`#` 全书标题、`##` 章、`###` 节、`####` 小节；
- 代码块必须标注语言：```` ```python ```` 而非 ```` ``` ````；
- 列表前最好有空行（脚本会自动补，但建议手动写规范）；
- 嵌套列表建议用 4 空格缩进（脚本会自动把 2 空格补为 4 空格）。

## HTML

- 使用 `templates/html_template.html`，已内置：
  - MathJax 3 加载与配置（行内 `\(...\)`、块级 `\[...\]`）；
  - 学术衬线字体（Source Serif / Charter / Georgia / 思源宋体）；
  - 暗色模式自动跟随系统；
  - 两个可折叠侧边栏：左上角"☰ 全书目录"按钮打开全书章节平级列表（当前章节高亮），右上角"☰ 本章目录"按钮打开当前页面的 h2/h3 小节大纲（脚本在页面加载时自动扫描正文生成，无需额外参数）；左侧全书目录仅当调用脚本时传入 `--toc-entry` 才会渲染；
  - 单章页面的章节导航：顶部是锁定在视口顶端的横幅（书名+当前章节标题居中且可点击返回目录，上一章/下一章分居两侧，章节名居中显示且不带章序号），底部是随文排布的"上一章 / 目录 / 下一章"收尾导航条，均支持左右方向键跳转——仅当调用脚本时传入相应参数才会渲染，详见下文"逐章 HTML 构建"；
  - 打印友好样式。
- 转换脚本 `templates/build_html.py` 已处理三个易错点：
  - 自动在列表前补空行；
  - 2 空格缩进的嵌套列表自动转 4 空格；
  - 数学公式中的 `<` `>` `&` 自动 HTML 实体转义——这一步至关重要：若不转义，浏览器 HTML 解析器会把 `$s<t$` 中的 `<t` 当成 HTML 标签起始符，破坏整个文档结构。

## 代码

- 标注语言（python / sql / r / cpp / ...）；
- 可运行性：除明确说明的"伪代码"外，所有代码须能在标准环境运行；
- 依赖在第一次出现时声明（如 `import numpy as np`）；
- 输出示例若有意义，应以注释形式给出。

## 图表

- 优先级：内嵌 SVG > matplotlib 生成的 PNG > 文字描述；
- SVG 须支持暗色模式（用 CSS 变量而非硬编码颜色）；
- 图表必须有编号和标题；
- 复杂概念图应分多张而非一张塞满。

## 交付物结构（标准交付包）

```
<交付目录>/
├── <book>_complet.md        # 合并版 markdown（front_matter + 各章 + 附录）
├── <book>_complet.html      # 合并版 HTML（单页，目录侧栏可导航全书）
├── outline.md               # 大纲
├── chapters/                # 逐章 markdown 源文件
│   ├── ch01.md ... chNN.md
├── chapters_html/           # 逐章 HTML
│   ├── index.html           # 目录页：链接到各分章页与合并版
│   ├── front_matter.html
│   ├── ch01.html ... chNN.html
│   └── appendix_*.html
└── appendix_*.md            # 附录 markdown（如有）
```

### 逐章 HTML 构建

对每个 md 单独调用 `build_html.py`，`--title` 取该文件首行 `#` 标题，`--header` 前缀加书名/级别便于分辨浏览器标签页，`--book-title` 传全书名字（显示在顶部横幅标题上方一行）。

**章节间跳转导航**：读者打开单章页面后，不应该每次都退回 `index.html` 再点下一章——用 `--prev-href/--prev-title`、`--next-href/--next-title`、`--index-href` 三组参数，为每个章节页面标注它在阅读顺序中的前后邻居和目录入口，脚本会渲染两条导航：页面顶部是**锁定在视口顶端、随滚动始终可见**的导航横幅（书名+当前章节标题居中，可点击标题返回目录；左右两侧分别是"上一章"/"下一章"，每侧第一行是方向标签、第二行是目标章节名——章节名会自动去掉"第N章"编号前缀，只显示标题正文），页面底部则是随文排布的一条"← 上一章 / 目录 / 下一章 →"收尾导航；两处都支持左右方向键翻章。三组参数都是可选的——都不传时（如构建目录页 `index.html` 本身或合并版）顶部横幅不会渲染（也不会占用额外的顶部留白），只传部分时缺失的一侧会显示为不可点击的占位符（用于全书第一章无上一章、最后一章无下一章的情况），不会导致布局跳动。

**左侧全书目录侧边栏**：用重复的 `--toc-entry "href|标题"` 参数（每章一个，按阅读顺序）为页面附上一份全书章节的平级列表，读者点开左上角"☰ 全书目录"按钮即可跳到任意章节，不必是相邻的上一章/下一章。哪个条目是"当前所在章节"由脚本自动判断——`--toc-entry` 里的 href 与本次构建的输出文件名相同的那一条会被高亮且不可点击。不传 `--toc-entry` 时左侧侧边栏（按钮和面板）整体不渲染。

按 front_matter → 各章 → 附录的阅读顺序建立一条导航链，为链上每个文件计算其前后邻居，并预先收集全书目录条目：

```bash
mkdir -p chapters_html
book_title="<书名>"
files=(front_matter.md chapters/ch*.md appendix_*.md)
n=${#files[@]}

# 预先收集全书目录条目（每个文件一条 "href|标题"），供每一页的 --toc-entry 复用
toc_args=()
for f in "${files[@]}"; do
  base=$(basename "$f" .md)
  t=$(head -1 "$f" | sed 's/^# *//')
  toc_args+=(--toc-entry "$base.html|$t")
done

for i in "${!files[@]}"; do
  f="${files[$i]}"
  base=$(basename "$f" .md)
  title=$(head -1 "$f" | sed 's/^# *//')
  args=(--title "$title" --header "$book_title · $title" --book-title "$book_title" \
        --index-href "index.html" "${toc_args[@]}")
  if [ "$i" -gt 0 ]; then
    prev_f="${files[$((i-1))]}"
    args+=(--prev-href "$(basename "$prev_f" .md).html" \
           --prev-title "$(head -1 "$prev_f" | sed 's/^# *//')")
  fi
  if [ "$i" -lt $((n-1)) ]; then
    next_f="${files[$((i+1))]}"
    args+=(--next-href "$(basename "$next_f" .md).html" \
           --next-title "$(head -1 "$next_f" | sed 's/^# *//')")
  fi
  python3 templates/build_html.py "$f" "chapters_html/$base.html" "${args[@]}"
done
```

若 `front_matter.md` 或 `appendix_*.md` 不存在，从 `files` 数组中去掉对应的 glob 即可（bash 通配符不匹配任何文件时会保留原始字符串，须确认文件存在后再展开，或改用显式文件列表）。

目录页 `index.html`：先用脚本生成一个 md（逐文件提取首行标题拼成链接列表，含指向 `../<book>_complet.html` 的合并版链接），再用同一脚本构建（不传 `--prev-href`/`--next-href`，避免目录页自己出现导航条；可以传 `--book-title`/`"${toc_args[@]}"` 以保持全书侧边栏风格一致），保持全套页面风格一致。

### 合并版构建

**不要裸 `cat`**：若前一文件末尾无空行，下一文件的 `# 标题` 会紧贴前文（最常见是紧贴表格行），python-markdown 不会把它解析为标题。用每个文件后补空行的方式拼接：

```bash
for f in front_matter.md chapters/ch*.md appendix_*.md; do
  cat "$f"; printf '\n'
done > <book>_complet.md
python3 templates/build_html.py <book>_complet.md <book>_complet.html --title "..." --header "..."
```

构建后抽查：合并 HTML 中每个应为 `<h1>` 的章/附录标题都真的渲染成了 `<h1>`（`grep -c '<h1'` 对比文件数）。

## 跨章引用

- 同册内：「见第 X 章 §X.Y」「参见习题 X.Y」「见例题 X.Y」；
- 跨册：「见上册第 X 章」「参见下册 §X.Y」。
