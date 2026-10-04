# Contributing

Start every page with one `#` heading: the site takes the page title from it.
Frontmatter is optional. Where a page needs it, the site reads `title`,
`description` and a nested `sidebar` block, which needs both `label` and
`order`:

```yaml
---
title: Long page title
description: One sentence for search results.
sidebar:
  label: Short label
  order: 10
---
```

For new files, use lowercase kebab case.

Run markdownlint locally before opening a pull request.

Discuss large structural changes in GitHub Issues before editing the tree.
