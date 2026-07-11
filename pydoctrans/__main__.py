"""pydoctrans 命令行入口。

用法::

    # 直接转换文档
    python -m pydoctrans convert input.docx output.pdf
    python -m pydoctrans convert input.docx -t pdf -o result

    # 启动 HTTP 服务
    python -m pydoctrans serve
    python -m pydoctrans serve --host 0.0.0.0 --port 8080
    python -m pydoctrans                      # 默认 = serve
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path


def _cmd_serve(args: argparse.Namespace) -> None:
    """启动 HTTP 服务。"""
    import uvicorn

    from pydoctrans.server import app

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger("pydoctrans")
    from pydoctrans import __version__

    logger.info("pydoctrans v%s starting on %s:%s", __version__, args.host, args.port)
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)


def _cmd_convert(args: argparse.Namespace) -> None:
    """命令行文档转换。"""
    from pydoctrans.convert import ConversionError, convert

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"错误: 输入文件不存在: {args.input}", file=sys.stderr)
        sys.exit(1)

    # 读取源文件
    data = input_path.read_bytes()

    # 确定文件名（用于 LO 识别文件类型）
    if args.file_name:
        file_name = args.file_name
    else:
        file_name = input_path.name

    # 确定输出路径和格式
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = None

    to = args.to
    if to is None and output_path is not None:
        # 从输出文件扩展名推断格式
        to = output_path.suffix.lstrip(".")
    if to is None:
        print("错误: 请通过 -t <格式> 或输出文件扩展名指定目标格式", file=sys.stderr)
        sys.exit(1)

    # 执行转换
    print(f"转换中: {input_path} → {to} ...")
    try:
        result = convert(
            data=data,
            to=to,
            file_name=file_name,
            timeout=args.timeout,
        )
    except ConversionError as e:
        print(f"转换失败: {e}", file=sys.stderr)
        sys.exit(1)
    except TimeoutError:
        print(f"转换超时 ({args.timeout}s)", file=sys.stderr)
        sys.exit(1)

    # 写入输出文件
    if output_path is None:
        # 默认输出文件名：源文件名 + 目标扩展名
        stem = input_path.stem
        output_path = Path.cwd() / f"{stem}.{to}"

    output_path.write_bytes(result)
    size = len(result)
    print(f"完成: {output_path} ({_format_size(size)})")


def _format_size(n: int) -> str:
    """将字节数格式化为人类可读字符串。"""
    if n < 1024:
        return f"{n} B"
    elif n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    else:
        return f"{n / (1024 * 1024):.1f} MB"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="pydoctrans — Python Document Transformer"
    )
    subparsers = parser.add_subparsers(
        dest="command",
        title="子命令",
    )

    # ---- convert 子命令 ----
    convert_parser = subparsers.add_parser(
        "convert",
        help="转换文档",
        description="将文档转换为其他格式",
    )
    convert_parser.add_argument(
        "input",
        help="输入文件路径",
    )
    convert_parser.add_argument(
        "output",
        nargs="?",
        default=None,
        help="输出文件路径（默认: <输入文件名>.<格式>）",
    )
    convert_parser.add_argument(
        "-t", "--to",
        default=None,
        help="目标格式（如 pdf、odt、docx）。未指定则从输出文件扩展名推断",
    )
    convert_parser.add_argument(
        "--file-name",
        default=None,
        help="覆盖传递给 LO 的文件名（用于无扩展名的输入文件）",
    )
    convert_parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="转换超时秒数（默认: 300）",
    )

    # ---- serve 子命令 ----
    serve_parser = subparsers.add_parser(
        "serve",
        help="启动 HTTP 服务",
        description="启动 pydoctrans HTTP API 服务",
    )
    serve_parser.add_argument(
        "--host",
        default=os.environ.get("HOST", "0.0.0.0"),
        help="监听地址（默认: 0.0.0.0）",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "8000")),
        help="监听端口（默认: 8000）",
    )
    serve_parser.add_argument(
        "--log-level",
        default=os.environ.get("LOG_LEVEL", "info"),
        choices=["debug", "info", "warning", "error"],
        help="日志级别（默认: info）",
    )

    args = parser.parse_args()

    if args.command == "convert":
        _cmd_convert(args)
    elif args.command == "serve":
        _cmd_serve(args)
    else:
        # 无子命令时默认启动服务，使用 serve 子解析器的默认值
        _cmd_serve(serve_parser.parse_args([]))


if __name__ == "__main__":
    main()
