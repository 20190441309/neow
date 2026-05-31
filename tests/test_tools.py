"""Tests for tools."""

import pytest

from neow.tools.file_ops import read_file, write_file, edit_file, create_file, delete_file, FileError
from neow.tools.command import execute_command, CommandError
from neow.tools.search import search_code, SearchError


class TestFileOps:
    """Tests for file operation tools."""

    def test_read_file(self, tmp_path):
        """Test reading a file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")
        result = read_file(str(test_file))
        # read_file now appends ¶PATH#HASH annotation
        assert result.startswith("Hello, World!")
        assert "¶" in result
        assert str(test_file) in result

    def test_read_file_not_found(self):
        """Test reading non-existent file."""
        with pytest.raises(FileError):
            read_file("/nonexistent/file.txt")

    def test_write_file(self, tmp_path):
        """Test writing a file."""
        test_file = tmp_path / "test.txt"

        result = write_file(str(test_file), "Hello, World!")
        assert test_file.read_text() == "Hello, World!"
        assert "successfully" in result.lower()

    def test_write_file_creates_dirs(self, tmp_path):
        """Test writing a file creates parent directories."""
        test_file = tmp_path / "subdir" / "test.txt"

        write_file(str(test_file), "Hello")
        assert test_file.read_text() == "Hello"

    def test_edit_file(self, tmp_path):
        """Test editing a file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        result = edit_file(str(test_file), "World", "Python")
        assert test_file.read_text() == "Hello, Python!"
        assert "successfully" in result.lower()

    def test_edit_file_not_found(self):
        """Test editing non-existent file."""
        with pytest.raises(FileError):
            edit_file("/nonexistent/file.txt", "old", "new")

    def test_edit_file_pattern_not_found(self, tmp_path):
        """Test editing file with non-existent pattern."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        with pytest.raises(FileError):
            edit_file(str(test_file), "NotFound", "Replacement")

    def test_edit_file_first_only(self, tmp_path):
        """Test editing file replaces only first occurrence when first_only=True."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("aaa\naaa\n")

        edit_file(str(test_file), "aaa", "bbb", first_only=True)
        assert test_file.read_text() == "bbb\naaa\n"

    def test_edit_file_with_line_range(self, tmp_path):
        """Test editing file within a line range."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nline2\nline3\nline4\nline5\n")

        edit_file(str(test_file), "line3", "LINE3", start_line=3, end_line=4)
        assert test_file.read_text() == "line1\nline2\nLINE3\nline4\nline5\n"

    def test_edit_file_start_line_only(self, tmp_path):
        """Test editing file from start_line to end."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nline2\nline3\n")

        edit_file(str(test_file), "line3", "LINE3", start_line=2)
        assert test_file.read_text() == "line1\nline2\nLINE3\n"

    def test_edit_file_end_line_only(self, tmp_path):
        """Test editing file from beginning to end_line."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nline2\nline3\n")

        edit_file(str(test_file), "line1", "LINE1", end_line=2)
        assert test_file.read_text() == "LINE1\nline2\nline3\n"

    def test_edit_file_line_range_out_of_bounds(self, tmp_path):
        """Test editing file with out-of-bounds line range."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nline2\n")

        with pytest.raises(FileError):
            edit_file(str(test_file), "x", "y", start_line=10)

    def test_edit_file_line_range_old_text_not_in_range(self, tmp_path):
        """Test editing file when old_text not in specified range."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nline2\nline3\n")

        with pytest.raises(FileError):
            edit_file(str(test_file), "line3", "LINE3", start_line=1, end_line=2)

    def test_create_file(self, tmp_path):
        """Test creating a new file."""
        test_file = tmp_path / "new.txt"

        result = create_file(str(test_file), "Hello")
        assert test_file.read_text() == "Hello"
        assert "successfully" in result.lower()

    def test_create_file_already_exists(self, tmp_path):
        """Test creating a file that already exists."""
        test_file = tmp_path / "existing.txt"
        test_file.write_text("content")

        with pytest.raises(FileError):
            create_file(str(test_file), "new content")

    def test_create_file_empty_content(self, tmp_path):
        """Test creating a file with empty content."""
        test_file = tmp_path / "empty.txt"

        create_file(str(test_file))
        assert test_file.read_text() == ""

    def test_create_file_creates_dirs(self, tmp_path):
        """Test creating a file creates parent directories."""
        test_file = tmp_path / "subdir" / "deep" / "new.txt"

        create_file(str(test_file), "content")
        assert test_file.read_text() == "content"

    def test_delete_file(self, tmp_path):
        """Test deleting a file."""
        test_file = tmp_path / "to_delete.txt"
        test_file.write_text("content")

        result = delete_file(str(test_file))
        assert not test_file.exists()
        assert "successfully" in result.lower()

    def test_delete_file_not_found(self):
        """Test deleting non-existent file."""
        with pytest.raises(FileError):
            delete_file("/nonexistent/file.txt")

    def test_delete_file_not_a_file(self, tmp_path):
        """Test deleting a directory path."""
        with pytest.raises(FileError):
            delete_file(str(tmp_path))


class TestCommand:
    """Tests for command execution tools."""

    def test_execute_command_success(self):
        """Test executing a successful command."""
        result = execute_command("echo hello")
        assert "hello" in result

    def test_execute_command_with_output(self):
        """Test executing command with output."""
        result = execute_command("python -c \"print('test')\"")
        assert "test" in result

    def test_execute_command_failure(self):
        """Test executing a failing command."""
        result = execute_command("nonexistent_command")
        assert result.startswith("Error:")

    def test_execute_command_timeout(self):
        """Test command timeout."""
        result = execute_command('python -c "import time; time.sleep(10)"', timeout=1)
        assert result.startswith("Error:")


class TestSearch:
    """Tests for code search tools."""

    def test_search_code(self, tmp_path):
        """Test searching code in files."""
        # Create test files
        (tmp_path / "test1.py").write_text("def hello():\n    print('hello')")
        (tmp_path / "test2.py").write_text("def world():\n    print('world')")

        results = search_code("hello", str(tmp_path))
        assert len(results) > 0
        assert any("hello" in r["content"] for r in results)

    def test_search_code_with_pattern(self, tmp_path):
        """Test searching code with file pattern."""
        (tmp_path / "test.py").write_text("def hello(): pass")
        (tmp_path / "test.txt").write_text("hello world")

        results = search_code("hello", str(tmp_path), file_pattern="*.py")
        assert len(results) == 1
        assert results[0]["file"].endswith(".py")

    def test_search_code_no_results(self, tmp_path):
        """Test searching with no results."""
        (tmp_path / "test.py").write_text("def hello(): pass")

        results = search_code("nonexistent", str(tmp_path))
        assert len(results) == 0

    def test_search_code_invalid_directory(self):
        """Test searching in invalid directory."""
        with pytest.raises(SearchError):
            search_code("test", "/nonexistent/directory")


class TestLintTestDetection:
    """Tests for lint and test auto-detection."""

    def test_detect_ruff_from_pyproject_toml(self, tmp_path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[tool.ruff]\nline-length = 88\n')
        from neow.tools.lint_test import detect_lint_command

        cmd = detect_lint_command(tmp_path)
        assert cmd is not None
        assert "ruff" in cmd

    def test_detect_eslint_from_config(self, tmp_path):
        eslintrc = tmp_path / ".eslintrc.json"
        eslintrc.write_text("{}")
        from neow.tools.lint_test import detect_lint_command

        cmd = detect_lint_command(tmp_path)
        assert cmd is not None
        assert "eslint" in cmd

    def test_detect_npm_lint_from_package_json(self, tmp_path):
        pkg = tmp_path / "package.json"
        pkg.write_text('{"scripts": {"lint": "eslint ."}}')
        from neow.tools.lint_test import detect_lint_command

        cmd = detect_lint_command(tmp_path)
        assert cmd is not None
        assert "npm run lint" in cmd

    def test_detect_makefile_lint(self, tmp_path):
        makefile = tmp_path / "Makefile"
        makefile.write_text("lint:\n\truff check .\n")
        from neow.tools.lint_test import detect_lint_command

        cmd = detect_lint_command(tmp_path)
        assert cmd is not None
        assert "make lint" in cmd

    def test_detect_no_lint(self, tmp_path):
        from neow.tools.lint_test import detect_lint_command

        cmd = detect_lint_command(tmp_path)
        assert cmd is None

    def test_detect_pytest(self, tmp_path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[tool.pytest.ini_options]\ntestpaths = ["tests"]\n')
        from neow.tools.lint_test import detect_test_command

        cmd = detect_test_command(tmp_path)
        assert cmd is not None
        assert "pytest" in cmd

    def test_detect_npm_test(self, tmp_path):
        pkg = tmp_path / "package.json"
        pkg.write_text('{"scripts": {"test": "jest"}}')
        from neow.tools.lint_test import detect_test_command

        cmd = detect_test_command(tmp_path)
        assert cmd is not None
        assert "npm test" in cmd

    def test_detect_makefile_test(self, tmp_path):
        makefile = tmp_path / "Makefile"
        makefile.write_text("test:\n\tpytest\n")
        from neow.tools.lint_test import detect_test_command

        cmd = detect_test_command(tmp_path)
        assert cmd is not None
        assert "make test" in cmd

    def test_detect_no_test(self, tmp_path):
        from neow.tools.lint_test import detect_test_command

        cmd = detect_test_command(tmp_path)
        assert cmd is None

    def test_run_lint_success(self, tmp_path):
        from neow.tools.lint_test import run_lint, LintResult

        result = run_lint(tmp_path, lint_command="echo 'no errors'")
        assert isinstance(result, LintResult)
        assert result.success is True

    def test_run_lint_failure(self, tmp_path):
        from neow.tools.lint_test import run_lint

        result = run_lint(tmp_path, lint_command="cmd /c exit 1")
        assert result.success is False

    def test_run_tests_success(self, tmp_path):
        from neow.tools.lint_test import run_tests, TestResult

        result = run_tests(tmp_path, test_command="echo 'all passed'")
        assert isinstance(result, TestResult)
        assert result.success is True

    def test_run_tests_failure(self, tmp_path):
        from neow.tools.lint_test import run_tests

        result = run_tests(tmp_path, test_command="cmd /c exit 1")
        assert result.success is False
