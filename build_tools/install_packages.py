#!/usr/bin/env python3
import argparse
import os
import sys
#from package_load import LoadPackages, logger
from packaging.linux.package_load import LoadPackages, logger

def main():
    parser = argparse.ArgumentParser(description="Install ROCm native build packages.")
    parser.add_argument("--dest-dir", required=True, help="Directory where built packages are located.")
    parser.add_argument("--package_json", required=True, help="Path to package.json.")
    parser.add_argument("--version", choices=["true", "false"], default="false", help="If true, install only versioned packages.")
    parser.add_argument("--composite", choices=["true", "false"], default="false", help="Install composite packages only.")
    parser.add_argument( "--amdgpu_family", type=str, required=False, help="Specify AMD GPU family (e.g., gfx94x).")

    args = parser.parse_args()

    version_flag = args.version.lower() == "true"
    composite_flag = args.composite.lower() == "true"
    amdgpu_family = args.amdgpu_family

    if amdgpu_family:
        amdgpu_family = amdgpu_family.split("-")[0]
    else:
        amdgpu_family = None

    pm = LoadPackages(args.package_json,amdgpu_family)
    non_comp, comp = pm.list_composite_packages()

    logger.info(f"Count of Composite packages: {len(comp)}")
    logger.info(f"Count of non Composite packages: {len(non_comp)}")
    if composite_flag:
        sorted_packages = pm.sort_packages_by_dependencies(comp)
    else:
        sorted_packages = pm.sort_packages_by_dependencies(non_comp)

    logger.info(f"Version flag: {version_flag}")

    pm.install_packages(args.dest_dir, sorted_packages,version_flag)

if __name__ == "__main__":
    main()

