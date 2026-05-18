"""Generate env files for eclipse v2 tasks that require pre-existing Eclipse projects."""
import os
from pathlib import Path

TASKS_ROOT = Path(__file__).parent

PROJECT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<projectDescription>
\t<name>{name}</name>
\t<comment></comment>
\t<projects>
\t</projects>
\t<buildSpec>
\t\t<buildCommand>
\t\t\t<name>org.eclipse.jdt.core.javabuilder</name>
\t\t\t<arguments>
\t\t\t</arguments>
\t\t</buildCommand>
\t</buildSpec>
\t<natures>
\t\t<nature>org.eclipse.jdt.core.javanature</nature>
\t</natures>
</projectDescription>
"""

CLASSPATH_DEFAULT = """<?xml version="1.0" encoding="UTF-8"?>
<classpath>
\t<classpathentry kind="src" path="src"/>
\t<classpathentry kind="con" path="org.eclipse.jdt.launching.JRE_CONTAINER"/>
\t<classpathentry kind="output" path="bin"/>
</classpath>
"""

def prefs(compliance: str) -> str:
    return (
        "eclipse.preferences.version=1\n"
        f"org.eclipse.jdt.core.compiler.codegen.targetPlatform={compliance}\n"
        f"org.eclipse.jdt.core.compiler.compliance={compliance}\n"
        f"org.eclipse.jdt.core.compiler.source={compliance}\n"
    )


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def make_project(task_id: str, project_name: str, compliance: str,
                 source_files: dict[str, str], extra_files: dict[str, str] | None = None,
                 custom_classpath: str | None = None) -> None:
    root = TASKS_ROOT / task_id / "env" / project_name
    write(root / ".project", PROJECT_XML.format(name=project_name))
    write(root / ".classpath", custom_classpath or CLASSPATH_DEFAULT)
    write(root / ".settings" / "org.eclipse.jdt.core.prefs", prefs(compliance))
    for rel, content in source_files.items():
        write(root / rel, content)
    if extra_files:
        for rel, content in extra_files.items():
            write(root / rel, content)


def build_all() -> None:
    # Task 2: LegacyApp — compliance=1.8
    make_project(
        "eclipse_v2_migrate_java_version",
        "LegacyApp",
        "1.8",
        {
            "src/legacy/LegacyService.java": (
                "package legacy;\n\n"
                "public class LegacyService {\n"
                "    public String greet(String name) {\n"
                "        return \"Hello, \" + name;\n"
                "    }\n\n"
                "    public static void main(String[] args) {\n"
                "        System.out.println(new LegacyService().greet(\"world\"));\n"
                "    }\n"
                "}\n"
            ),
        },
    )

    # Task 3: JsonTools — with lib/gson placeholder
    jar_placeholder = b"PK\x03\x04"  # minimal ZIP header so the "jar" is non-empty
    make_project(
        "eclipse_v2_add_external_jar_library",
        "JsonTools",
        "17",
        {
            "src/com/jsontools/JsonMain.java": (
                "package com.jsontools;\n\n"
                "public class JsonMain {\n"
                "    public static void main(String[] args) {\n"
                "        System.out.println(\"JsonTools ready\");\n"
                "    }\n"
                "}\n"
            ),
        },
    )
    jar_path = TASKS_ROOT / "eclipse_v2_add_external_jar_library" / "env" / "JsonTools" / "lib" / "gson-2.10.1.jar"
    jar_path.parent.mkdir(parents=True, exist_ok=True)
    # Create a minimal valid (empty) JAR (a zip with no entries).
    import zipfile
    with zipfile.ZipFile(jar_path, "w") as zf:
        zf.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")

    # Task 5: Shopping — old package with two classes
    make_project(
        "eclipse_v2_rename_package_refactor",
        "Shopping",
        "17",
        {
            "src/com/shop/old/CartItem.java": (
                "package com.shop.old;\n\n"
                "public class CartItem {\n"
                "    public String name;\n"
                "    public double price;\n"
                "    public int quantity;\n"
                "}\n"
            ),
            "src/com/shop/old/Product.java": (
                "package com.shop.old;\n\n"
                "public class Product {\n"
                "    public String sku;\n"
                "    public String description;\n"
                "    public double price;\n"
                "}\n"
            ),
        },
    )

    # Task 6: Unicode — compliance 17, no resources.prefs
    make_project(
        "eclipse_v2_configure_encoding_utf8",
        "Unicode",
        "17",
        {
            "src/uni/TextProcessor.java": (
                "package uni;\n\n"
                "public class TextProcessor {\n"
                "    public String normalize(String s) {\n"
                "        return s == null ? \"\" : s.trim();\n"
                "    }\n"
                "}\n"
            ),
        },
    )

    # Task 9: StrictMode — compliance 11
    make_project(
        "eclipse_v2_enable_warnings_as_errors",
        "StrictMode",
        "11",
        {
            "src/strict/Main.java": (
                "package strict;\n\n"
                "public class Main {\n"
                "    public static void main(String[] args) {\n"
                "        System.out.println(\"strict mode\");\n"
                "    }\n"
                "}\n"
            ),
        },
    )


def verify_all() -> None:
    import xml.etree.ElementTree as ET

    checks = [
        ("eclipse_v2_migrate_java_version", "LegacyApp",
         ["src/legacy/LegacyService.java"], "1.8"),
        ("eclipse_v2_add_external_jar_library", "JsonTools",
         ["src/com/jsontools/JsonMain.java", "lib/gson-2.10.1.jar"], "17"),
        ("eclipse_v2_rename_package_refactor", "Shopping",
         ["src/com/shop/old/CartItem.java", "src/com/shop/old/Product.java"], "17"),
        ("eclipse_v2_configure_encoding_utf8", "Unicode",
         ["src/uni/TextProcessor.java"], "17"),
        ("eclipse_v2_enable_warnings_as_errors", "StrictMode",
         ["src/strict/Main.java"], "11"),
    ]
    for task_id, project, files, compliance in checks:
        root = TASKS_ROOT / task_id / "env" / project
        assert (root / ".project").exists(), f"{task_id} missing .project"
        assert (root / ".classpath").exists(), f"{task_id} missing .classpath"
        assert (root / ".settings" / "org.eclipse.jdt.core.prefs").exists(), \
            f"{task_id} missing prefs"
        # Parse .project
        tree = ET.parse(root / ".project")
        name = tree.getroot().find("name").text
        assert name == project, f"{task_id} .project name {name} != {project}"
        # Parse .classpath
        ET.parse(root / ".classpath")
        # Parse prefs
        content = (root / ".settings" / "org.eclipse.jdt.core.prefs").read_text()
        assert f"compliance={compliance}" in content, \
            f"{task_id} wrong compliance: {content}"
        for f in files:
            p = root / f
            assert p.exists() and p.stat().st_size > 0, f"{task_id} missing {f}"
        print(f"OK {task_id}: {project}")


def write_manifests() -> None:
    import json
    manifests = {
        "eclipse_v2_migrate_java_version": {
            "project": "LegacyApp",
            "files": [
                (".project", None),
                (".classpath", None),
                (".settings/org.eclipse.jdt.core.prefs", None),
                ("src/legacy/LegacyService.java", None),
            ],
        },
        "eclipse_v2_add_external_jar_library": {
            "project": "JsonTools",
            "files": [
                (".project", None),
                (".classpath", None),
                (".settings/org.eclipse.jdt.core.prefs", None),
                ("src/com/jsontools/JsonMain.java", None),
                ("lib/gson-2.10.1.jar", "jar"),
            ],
        },
        "eclipse_v2_rename_package_refactor": {
            "project": "Shopping",
            "files": [
                (".project", None),
                (".classpath", None),
                (".settings/org.eclipse.jdt.core.prefs", None),
                ("src/com/shop/old/CartItem.java", None),
                ("src/com/shop/old/Product.java", None),
            ],
        },
        "eclipse_v2_configure_encoding_utf8": {
            "project": "Unicode",
            "files": [
                (".project", None),
                (".classpath", None),
                (".settings/org.eclipse.jdt.core.prefs", None),
                ("src/uni/TextProcessor.java", None),
            ],
        },
        "eclipse_v2_enable_warnings_as_errors": {
            "project": "StrictMode",
            "files": [
                (".project", None),
                (".classpath", None),
                (".settings/org.eclipse.jdt.core.prefs", None),
                ("src/strict/Main.java", None),
            ],
        },
    }
    for task_id, spec in manifests.items():
        project = spec["project"]
        files_list = []
        for rel, ftype in spec["files"]:
            files_list.append({
                "filename": f"{project}/{rel}",
                "sandbox_path": f"/home/user/workspace/{project}/{rel}",
                "type": ftype or rel.split(".")[-1] if "." in rel else "text",
            })
        manifest = {"task_id": task_id, "files": files_list}
        out_path = TASKS_ROOT / task_id / "env_manifest.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(manifest, indent=2))
        print(f"Manifest: {task_id}")


if __name__ == "__main__":
    build_all()
    verify_all()
    write_manifests()
    print("All env files generated and verified.")
