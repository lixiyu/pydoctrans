# API 参考

## convert()

```python
from pydoctrans import convert

pdf = convert(data, to="pdf", *, file_name="input.bin", timeout=None,
              before=None, after=None)
```

### 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `data` | `bytes` | *必填* | 源文件内容 |
| `to` | `str` | *必填* | 目标格式（`pdf`、`odt`、`docx` 等） |
| `file_name` | `str` | `"input.bin"` | 源文件名（含扩展名，LO 据此识别类型） |
| `timeout` | `int` | `None` | 超时秒数，`None` 使用默认值（300s） |
| `before` | `list[BeforeHook]` | `None` | 转换前钩子 |
| `after` | `list[AfterHook]` | `None` | 转换后钩子 |

### 返回值

`bytes` — 转换后的文件内容。

### 异常

| 异常 | 说明 |
|------|------|
| `ConversionError` | 转换失败（格式不支持、LO 崩溃等） |
| `TimeoutError` | 转换超时 |
| `ValueError` | 参数错误（如 file_name 缺少扩展名） |
| `HookExecutionError` | after 钩子执行失败 |

## ConversionContext

```python
from pydoctrans import ConversionContext
```

贯穿转换流程的上下文对象。

| 字段 | 类型 | 说明 |
|------|------|------|
| `data` | `bytes` | 文件内容（before 阶段为源文件，after 阶段为输出） |
| `file_name` | `str` | 源文件名 |
| `to` | `str` | 目标格式 |
| `engine` | `str` | 引擎名称 |
| `meta` | `dict` | 自由读写字典，钩子间传递状态 |

## 钩子

### BeforeHook

```python
from pydoctrans import BeforeHook

def my_hook(ctx: ConversionContext) -> None:
    ...
```

转换前执行。可以修改 `ctx.data`、`ctx.file_name`。抛出异常可中止转换。

### AfterHook

```python
from pydoctrans import AfterHook

def my_hook(ctx: ConversionContext) -> None:
    ...
```

转换后执行。可以修改 `ctx.data`（如加水印）、写入 `ctx.meta`（如记录上传 URL）。
