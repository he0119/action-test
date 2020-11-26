# action-test

测试操作

## 一些结果

release 事件触发时，使用的是那个标签的内容。

看起来通过 GitHub 发布打标签，是没有办法触发 push 事件的。

可以通过 `if: ${{ github.event_name == 'release' && github.event.action == 'published' }}` 来让一个任务仅在发布时运行。

`crazy-max/ghaction-docker-meta` 在 release 事件时，会同时输出 `"test/test:v0.1.5\ntest/test:latest"`。所以，正常的发布流程里，可以将 push 的 tags 触发给关闭。

## 完整的发布流程

1. 准备好需要发布的版本，推送到主分支，等待 Release Drafter 生成发布的草稿
2. 编辑并发布草稿，同时打上 tags
3. 等待操作自动编译，并部署
