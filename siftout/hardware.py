import os
import shutil
import glob
import logging
import re

logger = logging.getLogger(__name__)


class Janitor:
    def __init__(self, extra_patterns=None):
        self.trash_patterns = ["__pycache__", "*.log", "*.tmp", "*.temp"]
        if extra_patterns:
            if isinstance(extra_patterns, str):
                extra_patterns = [extra_patterns]
            self.trash_patterns.extend(extra_patterns)

    def list_trash(
        self,
    ):  # This Function prints out the list of all the trash elements present inside your folder
        found_items = []
        for pattern in self.trash_patterns:
            matches = glob.glob(f"**/{pattern}", recursive=True)
            found_items.extend(matches)

        # Remove duplicates in case multiple patterns match the same file
        found_items = list(set(found_items))

        if not found_items:
            logger.info("[Siftout] Workspace is already clean, No trash found!")
        else:
            logger.info("[Siftout] Found %d items to clean:", len(found_items))
            for item in found_items:
                logger.info(" - %s", item)

        return found_items

    def self_destruct(
        self,
    ):  # This function will delete the files which it detected in the function list_trash()
        items_to_kill = self.list_trash()
        files_cleaned = 0
        folders_cleaned = 0
        for thing in items_to_kill:
            try:
                if os.path.isdir(thing):  # Checks if it's a folder
                    shutil.rmtree(
                        thing
                    )  # This section removes the folders which can be moved to the trash bin
                    folders_cleaned += 1
                    logger.info("[Flux] removed %s folder", thing)
                elif os.path.isfile(thing):  # Checks if it's a file
                    os.remove(thing)
                    files_cleaned += 1
                    logger.info("[Flux] removed %s file", thing)
            except OSError as e:
                logger.error("Error removing %s: %s", thing, e)
        return {"files": files_cleaned, "folders": folders_cleaned}

    def secure_env(self):
        key_pattern = r'^([A-Z0-9_]+)\s*=\s*["\']([A-Za-z0-9_\-\.]{20,})["\']'

        py_files = glob.glob("**/*.py", recursive=True)
        env_entries = {}

        for file_path in py_files:
            # Skip standard system folders, virtual environments, and the package itself
            skip_dirs = {"siftout", "venv", ".venv", "env", ".env", "node_modules", ".git"}
            if (
                any(d in re.split(r"[\\/]", file_path) for d in skip_dirs)
                or "setup.py" in file_path
            ):
                continue
            updated_lines = []
            file_changed = False

            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            for lin_num, line in enumerate(lines, 1):
                match = re.search(key_pattern, line, re.IGNORECASE)

                if match:
                    var_name, secret_value = match.groups()
                    if len(secret_value) >= 20:
                        logger.warning(
                            f"[Siftout] Privacy Leak : {var_name} in {file_path}"
                        )

                        new_line = f"{var_name} = os.getenv('{var_name}')\n"
                        updated_lines.append(new_line)
                        env_entries[var_name] = secret_value
                        file_changed = True
                    else:
                        updated_lines.append(line)
                else:
                    updated_lines.append(line)
            if file_changed:

                if "import os" not in updated_lines[0]:
                    updated_lines.insert(0, "import os\n")

                with open(file_path, "w") as f:
                    f.writelines(updated_lines)

        if env_entries:
            self._update_env_file(env_entries)
            self._ensure_ignored(".env")

    def _update_env_file(self, env_entries):
        existing = {}

        if os.path.exists(".env"):
            with open(".env", "r") as f:
                for line in f:
                    if "=" in line:
                        k, v = line.strip().split("=", 1)
                        existing[k] = v

        with open(".env", "a") as f:
            for k, v in env_entries.items():
                if k not in existing:
                    f.write(f"{k}={v}\n")
                    logger.info(f"[Siftout] Added {k} to .env")
                    existing[k] = v

    def _ensure_ignored(self, file_name):
        mode = "a" if os.path.exists(".gitignore") else "w"

        already_ignored = False
        if mode == "a":
            with open(".gitignore", "r") as f:
                already_ignored = file_name in f.read()

        if not already_ignored:
            with open(".gitignore", mode) as f:
                f.write(f"\n{file_name}\n")
                logger.info(f"[Flux] added {file_name} to .gitignore")
