import argparse
import os
import sys
import unittest


def discover_and_run(target: str = None, verbosity: int = 2):
    tests_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests")

    if target:
        parts = target.split(".")
        module_name = parts[0]
        class_name = parts[1] if len(parts) > 1 else None
        method_name = parts[2] if len(parts) > 2 else None

        if not module_name.endswith(".py"):
            module_name = module_name + ".py"

        loader = unittest.TestLoader()
        suite = unittest.TestSuite()

        if method_name:
            suite.addTest(loader.loadTestsFromName(
                f"tests.{module_name[:-3]}.{class_name}.{method_name}"
            ))
        elif class_name:
            suite.addTest(loader.loadTestsFromName(
                f"tests.{module_name[:-3]}.{class_name}"
            ))
        else:
            suite.addTest(loader.loadTestsFromName(
                f"tests.{module_name[:-3]}"
            ))
    else:
        loader = unittest.TestLoader()
        suite = loader.discover(start_dir=tests_dir, pattern="test_*.py", top_level_dir=os.path.dirname(tests_dir))

    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


def main():
    parser = argparse.ArgumentParser(
        description="CBSS Tool 单元测试执行器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python run_unittest.py                              # 执行全部测试
  python run_unittest.py test_adb_manager             # 执行 test_adb_manager 模块全部测试
  python run_unittest.py test_adb_manager.TestADBManager  # 执行 TestADBManager 类全部测试
  python run_unittest.py test_adb_manager.TestADBManager.test_parse_success_output  # 执行单个测试方法
  python run_unittest.py -v 1                         # 简洁输出模式
        """.strip(),
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help="测试目标: [模块名] | [模块名.类名] | [模块名.类名.方法名]",
    )
    parser.add_argument(
        "-v", "--verbosity",
        type=int,
        default=2,
        choices=[0, 1, 2],
        help="输出详细级别 (0=静默, 1=简洁, 2=详细, 默认: 2)",
    )

    args = parser.parse_args()

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    exit_code = discover_and_run(target=args.target, verbosity=args.verbosity)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()