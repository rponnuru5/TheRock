#!/usr/bin/env python3
import argparse
import os
import platform
import subprocess
import sys
import json
import re

#!/usr/bin/env python3
import json
import os

def build_dependency_graph(packages, use_rpm=False):
    dep_key = "RPMRequires" if use_rpm else "DEBDepends"
    graph = {}
    pkg_names = {p["Package"] for p in packages if "Package" in p}

    for pkg in packages:
        name = pkg["Package"]
        deps = [d for d in pkg.get(dep_key, []) if d in pkg_names]
        graph[name] = deps
    return graph

def dfs_sort(graph):
    visited, sorted_list = set(), []

    def visit(pkg):
        if pkg in visited:
            return
        visited.add(pkg)
        for dep in graph.get(pkg, []):
            visit(dep)
        sorted_list.append(pkg)

    for pkg in graph:
        visit(pkg)
    return sorted_list

def sort_packages_by_dependencies(package_json_path,composite_names, use_rpm=False):

    with open(package_json_path, "r") as f:
        packages = json.load(f)

    composite = [pkg for pkg in packages if pkg["Package"] in composite_names]
    non_composite = [pkg for pkg in packages if pkg["Package"] not in composite_names]

    sorted_non = dfs_sort(build_dependency_graph(non_composite, use_rpm))
    sorted_composite = dfs_sort(build_dependency_graph(composite, use_rpm))

    return sorted_non, sorted_composite

def list_composite_packages(package_json_path):
    """
    Returns a list of package names that are marked as Composite: "Yes"
    from packaging/linux/package.json.
    Handles JSON structured as a list of package dicts.
    """
    with open(package_json_path, "r") as f:
        data = json.load(f)

    composite_packages = []
    non_composite_packages = []

    if isinstance(data, list):
        for pkg in data:
            # Ensure key exists and is string before comparing
            if str(pkg.get("Composite", "")).strip().lower() == "yes":
                pkg_name = pkg.get("Package", "").strip()
                if pkg_name:
                    composite_packages.append(pkg_name)
            else:
                pkg_name = pkg.get("Package", "").strip()
                if pkg_name:
                    non_composite_packages.append(pkg_name)
    else:
        print("Warning: Expected a list of packages in JSON, got something else.")


    return non_composite_packages,composite_packages


def detect_os_family():
    """Detect OS family (debian/redhat/suse/unknown)"""
    os_release = {}
    try:
        with open("/etc/os-release", "r") as f:
            for line in f:
                if "=" in line:
                    key, value = line.strip().split("=", 1)
                    os_release[key] = value.strip('"')
    except FileNotFoundError:
        system_name = platform.system().lower()
        if "linux" in system_name:
            return "linux"
        return "unknown"

    os_id = os_release.get("ID", "").lower()
    os_like = os_release.get("ID_LIKE", "").lower()

    if "ubuntu" in os_id or "debian" in os_like:
        return "debian"
    elif "rhel" in os_id or "centos" in os_id or "fedora" in os_like or "redhat" in os_like:
        return "redhat"
    elif "suse" in os_id or "sles" in os_id:
        return "suse"
    else:
        return "unknown"

def is_versioned_package(filename, base,version_flag):
    """
    Detects whether a package is versioned for a given base name.
    Example:
        base = "roctracer"
        filename = "roctracer7.0.0_7.0.0.70000_amd64.deb" -> True
    """
    base_esc = re.escape(base)

    if version_flag:
        # Versioned packages: base + version pattern
        # Example: roctracer7.0.0_7.0.0.70000_amd64.deb
        pattern = rf"^{base_esc}\d+\.\d+\.\d+_\d+\.\d+\.\d+"
    else:
        # Non-versioned packages: exact base + optional underscore + digits or .deb/.rpm
        # Excludes versioned packages and packages with extra suffix like -dev
        pattern = rf"^{base_esc}_\d+\.\d+\.\d+"

    return re.search(pattern, filename) is not None

def load_package_order(json_path,composite_flag):
    with open(json_path, "r") as f:
        data = json.load(f)
    if composite_flag:
        return data.get("composite_order", [])
    else:
        return data.get("noncomposite_order", [])

def find_packages_for_base(dest_dir, base, version_flag):
    """
    Retrieve packages matching the base name from dest_dir based on version_flag.
    """
    all_files = [f for f in os.listdir(dest_dir) if f.endswith((".deb", ".rpm"))]
    matched = []

    for f in all_files:
        if f.startswith(base):
            if version_flag:
                if is_versioned_package(f, base,version_flag):
                    matched.append(os.path.join(dest_dir, f))

            else:
                if is_versioned_package(f, base,False):
                    matched.append(os.path.join(dest_dir, f))
                if is_versioned_package(f, base,True):
                    matched.append(os.path.join(dest_dir, f))
    # Sort: versioned first
    matched.sort(key=lambda x: (not is_versioned_package(os.path.basename(x), base,True), x))
    return matched

def install_packages(dest_dir, package_order_file, version_flag,composite_flag):
    os_family = detect_os_family()
    print(f"Detected OS family: {os_family}")
    print(f"Version flag: {version_flag}")
    if not os.path.isdir(dest_dir):
        print(f"Artifacts directory not found: {dest_dir}")
        return

    rpmorder = load_package_order(package_order_file,composite_flag)
    final_install_list = []
    composite_packages = []

    non_composite_packages,composite_packages = list_composite_packages("build_tools/packaging/linux/package.json")
    sorted_non_composite_packages,sorted_composite_packages = sort_packages_by_dependencies("build_tools/packaging/linux/package.json",composite_packages,False)

    if os_family == "debian":
        sorted_composite_packages = [re.sub('-devel$', '-dev', word) for word in sorted_composite_packages]
        sorted_non_composite_packages = [re.sub('-devel$', '-dev', word) for word in sorted_non_composite_packages]


    print(f"Non-composite packages count: {len(non_composite_packages)}")
    print(f"Composite packages count: {len(composite_packages)}")
    print(f"sorted Non-composite packages count: {len(sorted_non_composite_packages)}")
    print(f"sorted Composite packages count: {len(sorted_composite_packages)}")

    if composite_flag:
        print(f"composite packages installation")
        for base in sorted_composite_packages:
            pkgs = find_packages_for_base(dest_dir, base, version_flag)
            if pkgs:
                final_install_list.extend(pkgs)
            else:
                print("pkgs=",pkgs,base)
    else:
        print(f"non composite packages installation")
        for base in sorted_non_composite_packages:
            pkgs = find_packages_for_base(dest_dir, base, version_flag)
            if pkgs:
                if len(pkgs) > 2:
                    print("pkgs=",len(pkgs),base)
                final_install_list.extend(pkgs)
            else:
                print("pkgs=",pkgs,base)

    print(f"final_install_list packages count: {len(final_install_list)}")
    #print(f"final_install_list packages : {final_install_list}")


    if not final_install_list:
        print("No packages to install based on version flag and order.")
        return

    print("\nInstalling packages in order...\n")

    for pkg_path in final_install_list:
        print(f"Installing: {os.path.basename(pkg_path)}")
        if os_family == "debian":
            subprocess.run(["sudo", "dpkg", "-i", pkg_path], check=False)
        elif os_family == "redhat":
            subprocess.run(["sudo", "rpm", "-ivh", "--replacepkgs", pkg_path], check=False)
        elif os_family == "suse":
            subprocess.run(["sudo", "zypper", "--non-interactive", "install", "--replacepkgs", pkg_path], check=False)
        else:
            print(f"Unsupported OS for package: {pkg_path}")

    if os_family == "debian":
        # Fix dependencies
        subprocess.run(["sudo", "apt-get", "-f", "install", "-y"], check=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Install ROCm native build packages.")
    parser.add_argument("--dest-dir", required=True, help="Directory where built packages are located.")
    parser.add_argument("--package-order", required=True, help="Path to package_order.json")
    parser.add_argument("--os", help="Optional manual override for OS type (debian, redhat, suse)")
    parser.add_argument("--version", choices=["true", "false"], default="false",
                        help="If true, install only versioned packages (e.g., roctracer7.0.0_7.0.0.70000...)")
    parser.add_argument("--composite", choices=["true", "false"], default="false",
                        help="If true, install only versioned packages (e.g., roctracer7.0.0_7.0.0.70000...)")
    args = parser.parse_args()

    dest_dir = args.dest_dir
    os_type = args.os.lower() if args.os else detect_os_family()
    version_flag = args.version.lower() == "true"
    composite_flag = args.composite.lower() == "true"

    print(f"Detected or provided OS type: {os_type}")
    print(f"Using artifacts from: {dest_dir}")
    print(f"Version flag: {version_flag}")

    if not os.path.isdir(dest_dir):
        print(f"Directory not found: {dest_dir}")
        sys.exit(1)

    install_packages(dest_dir, args.package_order, version_flag,composite_flag)

