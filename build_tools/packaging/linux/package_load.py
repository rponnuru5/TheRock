#!/usr/bin/env python3
import json
import os
import re
import subprocess
import platform
import logging

LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO, datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger("package_load")


class LoadPackages:
    def __init__(self, package_json_path: str,amdgpu_family: str = None):
        self.package_json_path = package_json_path
        self.amdgpu_family = amdgpu_family
        self.packages = self._load_packages()
        self.packages_arch = self._load_packages_arch()
        self.os_family = self.detect_os_family()
        self.pkg_map = {pkg["Package"]: pkg for pkg in self.packages}

    # ---------------------------------------------------------------------
    # Core JSON and Package Utilities
    # ---------------------------------------------------------------------
    def _load_packages(self):
        with open(self.package_json_path, "r") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError("Expected a list of package objects in JSON.")
        return data

    def arch_suffix_flag(self,package_name):
        """
        Given a list of package dicts, returns a list of package names.
        Rules:
          - If 'Gfxarch' is True and amdgpu_family is provided, append '-<amdgpu_family>'.
          - Do not append if package name contains 'devel'.
        """
        pkg = self.pkg_map.get(package_name)
        if not pkg:
            # fallback: if package not found in self.packages, leave as is
            return package_name
        gfx_arch_flag = str(pkg.get("Gfxarch", "False")).lower() == "true"

        return gfx_arch_flag 

    def _load_packages_arch(self):
        """
        Returns a list of package names.
        If 'Gfxarch' is True and amdgpu_family is provided, append '-<amdgpu_family>'.
        """
        packages_arch = []

        for pkg in self.packages:
            name = pkg.get("Package")
            gfx_arch_flag = str(pkg.get("Gfxarch", "False")).lower() == "true"

            #if gfx_arch_flag and self.amdgpu_family:
            if gfx_arch_flag and self.amdgpu_family and "devel" not in name:
                name = f"{name}-{self.amdgpu_family}"

            packages_arch.append(name)

        return packages_arch

    def list_composite_packages(self):
        """Return (non_composite, composite) package lists."""
        composite = []
        non_composite = []
        for pkg in self.packages:
            name = pkg.get("Package", "").strip()
            if not name:
                continue
            if str(pkg.get("Composite", "")).strip().lower() == "yes":
                composite.append(name)
            else:
                non_composite.append(name)
        return non_composite, composite

    def _build_dependency_graph(self, packages, use_rpm=False):
        dep_key = "RPMRequires" if use_rpm else "DEBDepends"
        graph = {}
        pkg_names = {p["Package"] for p in packages if "Package" in p}

        for pkg in packages:
            name = pkg["Package"]
            deps = [d for d in pkg.get(dep_key, []) if d in pkg_names]
            graph[name] = deps
        return graph

    def _dfs_sort(self, graph):
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

    def sort_packages_by_dependencies(self, pacakge_names, use_rpm=False):

        packages = [pkg for pkg in self.packages if pkg["Package"] in pacakge_names]

        sorted_pacakges = self._dfs_sort(self._build_dependency_graph(packages, use_rpm))

        if self.os_family == "debian":
            sorted_pacakges = [re.sub('-devel$', '-dev', word) for word in sorted_pacakges]

        return sorted_pacakges

    # ---------------------------------------------------------------------
    # OS & Installation Helpers
    # ---------------------------------------------------------------------
    def detect_os_family(self):
        """Detect OS family (debian/redhat/suse/unknown)."""
        os_release = {}
        try:
            with open("/etc/os-release", "r") as f:
                for line in f:
                    if "=" in line:
                        k, v = line.strip().split("=", 1)
                        os_release[k] = v.strip('"')
        except FileNotFoundError:
            system_name = platform.system().lower()
            return "linux" if "linux" in system_name else "unknown"

        os_id = os_release.get("ID", "").lower()
        os_like = os_release.get("ID_LIKE", "").lower()

        if "ubuntu" in os_id or "debian" in os_like:
            return "debian"
        elif any(x in os_id for x in ["rhel", "centos"]) or "fedora" in os_like or "redhat" in os_like:
            return "redhat"
        elif "suse" in os_id or "sles" in os_id:
            return "suse"
        else:
            return "unknown"

    def is_versioned_package(self, filename, base, version_flag,arch_flag):
        base_esc = re.escape(base)

            # Lookup package to check gfx_arch_flag
        pkg = self.pkg_map.get(base, {})
        gfx_arch_flag = str(pkg.get("Gfxarch", "False")).lower() == "true"

        # Only add amdgpu_suffix if conditions are met
        amdgpu_suffix = ""
        if gfx_arch_flag and self.amdgpu_family and "devel" not in base.lower():
            amdgpu_suffix = re.escape(self.amdgpu_family)

        if version_flag:
            if amdgpu_suffix:
                # Example: hipsolver7.0.0-gfx94x_7.0.0.70000
                pattern = rf"^{base_esc}\d+\.\d+\.\d+-{amdgpu_suffix}_\d+\.\d+\.\d+"
            else:
                # Versioned package without GPU suffix
                pattern = rf"^{base_esc}\d+\.\d+\.\d+_\d+\.\d+\.\d+"
        else:
            if amdgpu_suffix:
                # Non-versioned package with GPU suffix
                pattern = rf"^{base_esc}-{amdgpu_suffix}_?\d+\.\d+\.\d+"
            else:
                # Non-versioned package without GPU suffix
                pattern = rf"^{base_esc}_?\d+\.\d+\.\d+"

        return re.search(pattern, filename) is not None


    def find_packages_for_base(self, dest_dir, base, version_flag):
        all_files = [f for f in os.listdir(dest_dir) if f.endswith((".deb", ".rpm"))]
        matched = []

        for f in all_files:
            if f.startswith(base):
                arch_flag = self.arch_suffix_flag(base)
                if version_flag:
                    if self.is_versioned_package(f, base,version_flag,arch_flag):
                        matched.append(os.path.join(dest_dir, f))
                else:
                    if self.is_versioned_package(f, base,False,arch_flag):
                        matched.append(os.path.join(dest_dir, f))
                    if self.is_versioned_package(f, base,True,arch_flag):
                        matched.append(os.path.join(dest_dir, f))
        # Sort: versioned first
        matched.sort(key=lambda x: (not self.is_versioned_package(os.path.basename(x), base,True,arch_flag), x))
        return matched

    # ---------------------------------------------------------------------
    # Install Logic
    # ---------------------------------------------------------------------
    def install_packages(self, dest_dir, sorted_packages, version_flag):
        os_family = self.detect_os_family()
        logger.info(f"Detected OS family: {os_family}")

        if not os.path.isdir(dest_dir):
            logger.error(f"Artifacts directory not found: {dest_dir}")
            return


        final_install_list = []
        for base in sorted_packages:
            pkgs = self.find_packages_for_base(dest_dir, base, version_flag)
            if pkgs:
                final_install_list.extend(pkgs)
            else:
                logger.error(f"No matching package found for: {base}")

        logger.info(f"Final install list count: {len(final_install_list)}")

        #logger.info(f"sorted_packages: {(final_install_list)}")
        if not final_install_list:
            logger.warning("No packages to install based on filters.")
            return

        #logger.info(f"sorted_packages: {(final_install_list)}")

        for pkg_path in final_install_list:
            pkg_name = os.path.basename(pkg_path)
            logger.info(f"Installing: {pkg_name}")
            try:
                if os_family == "debian":
                    result = subprocess.run(["sudo", "dpkg", "-i", pkg_path], capture_output=True, text=True)
                elif os_family == "redhat":
                    result = subprocess.run(["sudo", "rpm", "-ivh", "--replacepkgs", pkg_path], capture_output=True, text=True)
                elif os_family == "suse":
                    result = subprocess.run(["sudo", "zypper", "--non-interactive", "install", "--replacepkgs", pkg_path], capture_output=True, text=True)
                else:
                    logger.error(f"Unsupported OS for {pkg_path}")
                    continue

                if result.returncode != 0:
                    logger.error(f"Failed to install {pkg_name}: {result.stderr.strip()}")
                else:
                    logger.info(f"✅ Installed {pkg_name}")

            except Exception as e:
                logger.exception(f"Exception installing {pkg_name}: {e}")

