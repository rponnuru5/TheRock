#!/usr/bin/env python3
import argparse
import os
import platform
import subprocess
import sys
import json
import re

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

def is_versioned_package(filename, base):
    """
    Detects whether a package is versioned for a given base name.
    Example:
        base = "roctracer"
        filename = "roctracer7.0.0_7.0.0.70000_amd64.deb" -> True
    """
    base_esc = re.escape(base)
    pattern = rf"^{base_esc}[0-9]+\.[0-9]+\.[0-9]+_[0-9]+\.[0-9]+\.[0-9]+"
    return re.search(pattern, filename) is not None

def load_package_order(json_path):
    with open(json_path, "r") as f:
        data = json.load(f)
    return data.get("rpmorder", [])

def find_packages_for_base(dest_dir, base, version_flag):
    """
    Retrieve packages matching the base name from dest_dir based on version_flag.
    """
    all_files = [f for f in os.listdir(dest_dir) if f.endswith((".deb", ".rpm"))]
    matched = []

    for f in all_files:
        # Exact match: base is prefix before any version or underscore
        if f.startswith(base):
            if version_flag:
                if is_versioned_package(f, base):
                    matched.append(os.path.join(dest_dir, f))
            else:
                matched.append(os.path.join(dest_dir, f))
    # Sort: versioned first
    matched.sort(key=lambda x: (not is_versioned_package(os.path.basename(x), base), x))
    return matched

def install_packages(dest_dir, package_order_file, version_flag):
    os_family = detect_os_family()
    print(f"Detected OS family: {os_family}")
    print(f"Version flag: {version_flag}")
    if not os.path.isdir(dest_dir):
        print(f"Artifacts directory not found: {dest_dir}")
        return

    rpmorder = load_package_order(package_order_file)
    final_install_list = []

    for base in rpmorder:
        pkgs = find_packages_for_base(dest_dir, base, version_flag)
        final_install_list.extend(pkgs)

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
    args = parser.parse_args()

    dest_dir = args.dest_dir
    os_type = args.os.lower() if args.os else detect_os_family()
    version_flag = args.version.lower() == "true"

    print(f"Detected or provided OS type: {os_type}")
    print(f"Using artifacts from: {dest_dir}")
    print(f"Version flag: {version_flag}")

    if not os.path.isdir(dest_dir):
        print(f"Directory not found: {dest_dir}")
        sys.exit(1)

    install_packages(dest_dir, args.package_order, version_flag)

