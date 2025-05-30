from conan import ConanFile
from conan.errors import ConanInvalidConfiguration
from conan.tools.apple import is_apple_os
from conan.tools.build import check_min_cppstd, cross_building
from conan.tools.cmake import CMake, CMakeDeps, CMakeToolchain, cmake_layout
from conan.tools.files import (
    apply_conandata_patches,
    collect_libs,
    get,
    rmdir,
    load,
    save,
    copy,
    export_conandata_patches,
    rm,
    rename,
    replace_in_file
)
from conan.tools.microsoft import is_msvc, msvc_runtime_flag
from conan.tools.scm import Version

import json
import os
from pathlib import Path, PurePosixPath
import re
import textwrap


required_conan_version = ">=1.62.0"

# LLVM's default config is to enable all targets, but end users can significantly reduce
# build times for the package by specifying only the targets they need as a
# semi-colon delimited string in the value of the 'targets' option
LLVM_TARGETS = {
    "AArch64",
    "AMDGPU",
    "ARM",
    "AVR",
    "BPF",
    "Hexagon",
    "Lanai",
    "LoongArch",
    "Mips",
    "MSP430",
    "NVPTX",
    "PowerPC",
    "RISCV",
    "Sparc",
    "SystemZ",
    "VE",
    "WebAssembly",
    "X86",
    "XCore"
}

def components_from_dotfile(dotfile):
    """
    Parse the dotfile generated by the
    [cmake --graphviz](https://cmake.org/cmake/help/latest/module/CMakeGraphVizOptions.html)
    option to generate the list of available LLVM CMake targets and their inter-component dependencies.

    In future a [CPS](https://cps-org.github.io/cps/index.html) format could be used, or generated directly
    by the LLVM build system
    """
    def node_labels(dot):
        """
        match each node in the dotfile with a label property, and map the label to a conan component
        """
        label_replacements = {
            "LibXml2::LibXml2": "libxml2::libxml2",
            "ZLIB::ZLIB": "zlib::zlib",
            "zstd::libzstd_static": "zstd::zstdlib",
            "-lpthread": "pthread"
        }
        for row in dot:
            match_label = re.match(r'''^\s*"(node[0-9]+)"\s*\[\s*label\s*=\s*"(.+)".*''', row)
            if match_label:
                node = match_label.group(1)
                label = match_label.group(2)
                yield node, label_replacements.get(label, label)

    def node_dependencies(dot):
        """
        Using the nodes with labels, extract the component dependencies of each node
        """
        ignore_deps = [
            "diaguids.lib" # https://github.com/llvm/llvm-project/issues/86250
        ]
        labels = {k: v for k, v in node_labels(dot)}
        for row in dot:
            match_dep = re.match(r'''^\s*"(node[0-9]+)"\s*->\s*"(node[0-9]+)".*''', row)
            if match_dep:
                node_label = labels[match_dep.group(1)]
                dependency = labels[match_dep.group(2)]
                if node_label.startswith("LLVM") and PurePosixPath(dependency).parts[-1] not in ignore_deps:
                    yield node_label, labels[match_dep.group(2)]
        # some components don't have dependencies
        for label in labels.values():
            if label.startswith("LLVM"):
                yield label, None

    system_libs = {
        "ole32",
        "delayimp",
        "shell32",
        "advapi32",
        "-delayload:shell32.dll",
        "uuid",
        "psapi",
        "-delayload:ole32.dll",
        "ntdll",
        "ws2_32",
        "rt",
        "m",
        "dl",
        "pthread"
    }
    components = {}
    dotfile_rows = dotfile.split("\n")
    for node, dependency in node_dependencies(dotfile_rows):
        key = "system_libs" if dependency in system_libs else "requires"
        if not node in components:
            components[node] = { "system_libs": [], "requires": [] }
            if dependency is not None:
                components[node][key] = [dependency]
        elif dependency is not None:
            components[node][key].append(dependency)

    return components


class LLVMCoreConan(ConanFile):
    name = "llvm-core"
    description = (
        "A toolkit for the construction of highly optimized compilers,"
        "optimizers, and runtime environments."
    )
    package_type = "library"
    license = "Apache-2.0 WITH LLVM-exception"
    topics = ("llvm", "compiler")
    homepage = "https://llvm.org"
    url = "https://github.com/conan-io/conan-center-index"
    settings = "os", "arch", "compiler", "build_type"
    options = {
        "shared": [True, False],
        "fPIC": [True, False],
        "components": ["ANY"],
        "targets": ["ANY"],
        "exceptions": [True, False],
        "rtti": [True, False],
        "threads": [True, False],
        "lto": ["On", "Off", "Full", "Thin"],
        "static_stdlib": [True, False],
        "unwind_tables": [True, False],
        "expensive_checks": [True, False],
        "use_perf": [True, False],
        "use_sanitizer": [
            "Address",
            "Memory",
            "MemoryWithOrigins",
            "Undefined",
            "Thread",
            "DataFlow",
            "Address;Undefined",
            "None"
        ],
        "with_ffi": [True, False],
        "with_libedit": [True, False],
        "with_terminfo": [True, False],
        "with_zlib": [True, False],
        "with_xml2": [True, False],
        "with_z3": [True, False],
        "with_zstd": [True, False],
    }
    default_options = {
        "shared": False,
        "fPIC": True,
        "components": "all",
        "targets": "all",
        "exceptions": True,
        "rtti": True,
        "threads": True,
        "lto": "Off",
        "static_stdlib": False,
        "unwind_tables": True,
        "expensive_checks": False,
        "use_perf": False,
        "use_sanitizer": "None",
        "with_libedit": True,
        "with_ffi": False,
        "with_terminfo": False,  # differs from LLVM default
        "with_xml2": True,
        "with_z3": True,
        "with_zlib": True,
        "with_zstd": True,
    }

    @property
    def _min_cppstd(self):
        if Version(self.version) >= 19:
            return 17
        return 14

    @property
    def _compilers_minimum_version(self):
        return {14: {
            "apple-clang": "10",
            "clang": "3.4",
            "gcc": "5",
            "msvc": "191",
            "Visual Studio": "15",
        }, 17: {
            "apple-clang": "10",
            "clang": "6",
            "gcc": "7",
            "msvc": "192",
            "Visual Studio": "16",
        },
        }.get(self._min_cppstd, {})

    def export_sources(self):
        export_conandata_patches(self)

    def config_options(self):
        if self.settings.os == "Windows":
            del self.options.fPIC
            del self.options.with_libedit  # not supported on windows
        if Version(self.version) < 15:
            # Added by https://reviews.llvm.org/D128465
            del self.options.with_zstd
        if Version(self.version) >= 19:
            # removed in https://github.com/llvm/llvm-project/commit/852aaf54071ad072335dcac57f544d4da34c875a
            del self.options.with_terminfo

    def configure(self):
        if self.options.shared:
            self.options.rm_safe("fPIC")

    def layout(self):
        cmake_layout(self, src_folder="src")

    def requirements(self):
        if self.options.with_ffi:
            self.requires("libffi/3.4.6")
        if self.options.get_safe("with_libedit"):
            self.requires("editline/3.1")
        if self.options.with_zlib:
            self.requires("zlib/[>=1.2.11 <2]")
        if self.options.with_xml2:
            self.requires("libxml2/[>=2.12.5 <3]")
        if self.options.with_z3:
            self.requires("z3/4.13.0")
        if self.options.get_safe("with_zstd"):
            self.requires("zstd/1.5.6")

    def build_requirements(self):
        self.tool_requires("ninja/[>=1.10.2 <2]")
        self.tool_requires("cmake/[>=3.20 <4]") # required by LLVM 19

    def validate(self):
        if self.settings.compiler.cppstd:
            check_min_cppstd(self, self._min_cppstd)
        minimum_version = self._compilers_minimum_version.get(str(self.settings.compiler), False)
        if minimum_version and Version(self.settings.compiler.version) < minimum_version:
            raise ConanInvalidConfiguration(
                f"{self.ref} requires C++{self._min_cppstd}, which your compiler does not support."
            )

        if self.options.shared:
            if self.settings.os == "Windows":
                raise ConanInvalidConfiguration("Shared builds are currently not supported on Windows")
            if is_apple_os(self) and self.options.with_xml2 and bool(self.dependencies["libxml2"].options.iconv):
                # FIXME iconv contains duplicate symbols in the libiconv and libcharset libraries (both of which are
                #  provided by libiconv). This may be an issue with how conan packages libiconv
                raise ConanInvalidConfiguration("iconv cannot be linked into the shared LLVM library on macos "
                                                    "due to duplicate symbols. Use libxml2/*:iconv=False.")

        if self.options.exceptions and not self.options.rtti:
            raise ConanInvalidConfiguration("Cannot enable exceptions without rtti support")

        if cross_building(self):
            # FIXME support cross compilation
            #  For Cross Building, LLVM builds a "native" toolchain in a subdirectory of the main build directory.
            #  This subdirectory would need to have the conan cmake configuration files for the build platform
            #  installed into it for a cross build to be successful.
            #  see also https://llvm.org/docs/HowToCrossCompileLLVM.html
            raise ConanInvalidConfiguration("Cross compilation is not supported. Contributions are welcome!")

    def validate_build(self):
        if os.getenv("CONAN_CENTER_BUILD_SERVICE") and self.settings.build_type == "Debug":
            if self.settings.os == "Linux":
                raise ConanInvalidConfiguration("Debug build is not supported on CCI due to resource limitations")
            elif self.options.shared:
                raise ConanInvalidConfiguration("Shared Debug build is not supported on CCI due to resource limitations")

    def source(self):
        sources = self.conan_data["sources"][self.version]
        if Version(self.version) < 15:
            get(self, **sources, strip_root=True)
        else:
            # LLVM >=15 split up several components in its release, including cmake
            get(self, **sources["llvm"], destination='llvm-main', strip_root=True)
            get(self, **sources["cmake"], destination='cmake', strip_root=True)

    def _apply_resource_limits(self, cmake_definitions):
        if os.getenv("CONAN_CENTER_BUILD_SERVICE"):
            self.output.info("Applying CCI Resource Limits")
            default_ram_per_compile_job = 16384
            default_ram_per_link_job = 2048
        else:
            default_ram_per_compile_job = None
            default_ram_per_link_job = None

        ram_per_compile_job = self.conf.get("user.llvm-core:ram_per_compile_job", default_ram_per_compile_job)
        if ram_per_compile_job:
            cmake_definitions["LLVM_RAM_PER_COMPILE_JOB"] = ram_per_compile_job

        ram_per_link_job = self.conf.get("user.llvm-core:ram_per_link_job", default_ram_per_link_job)
        if ram_per_link_job:
            cmake_definitions["LLVM_RAM_PER_LINK_JOB"] = ram_per_link_job

    @property
    def _targets_to_build(self):
        return self.options.targets if self.options.targets != "all" else self._all_targets

    @property
    def _all_targets(self):
        targets = LLVM_TARGETS if Version(self.version) >= 14 else LLVM_TARGETS - {"LoongArch", "VE"}
        return ";".join(targets)

    def generate(self):
        tc = CMakeToolchain(self, generator="Ninja")
        # https://releases.llvm.org/12.0.0/docs/CMake.html
        # https://releases.llvm.org/13.0.0/docs/CMake.html
        # https://releases.llvm.org/19.1.0/docs/CMake.html
        cmake_variables = {
            # Enables LLVM to find conan libraries during try_compile
            "CMAKE_TRY_COMPILE_CONFIGURATION": str(self.settings.build_type),
            # LLVM has two separate concepts of a "shared library build".
            # "BUILD_SHARED_LIBS" builds shared versions of all the static components
            # "LLVM_BUILD_LLVM_DYLIB" builds a single shared library containing all components.
            # It is likely the latter that the user expects by a "shared library" build.
            "BUILD_SHARED_LIBS": False,
            "LLVM_BUILD_LLVM_DYLIB": self.options.shared,
            "LLVM_LINK_LLVM_DYLIB": self.options.shared,
            "LLVM_DYLIB_COMPONENTS": self.options.components,
            "LLVM_ABI_BREAKING_CHECKS": "WITH_ASSERTS",
            "LLVM_INCLUDE_BENCHMARKS": False,
            "LLVM_INCLUDE_TOOLS": True,
            "LLVM_INCLUDE_EXAMPLES": False,
            "LLVM_INCLUDE_TESTS": False,
            "LLVM_ENABLE_IDE": False,
            "LLVM_ENABLE_EH": self.options.exceptions,
            "LLVM_ENABLE_RTTI": self.options.rtti,
            "LLVM_ENABLE_THREADS": self.options.threads,
            "LLVM_ENABLE_LTO": self.options.lto,
            "LLVM_STATIC_LINK_CXX_STDLIB": self.options.static_stdlib,
            "LLVM_ENABLE_UNWIND_TABLES": self.options.unwind_tables,
            "LLVM_ENABLE_EXPENSIVE_CHECKS": self.options.expensive_checks,
            "LLVM_ENABLE_ASSERTIONS": str(self.settings.build_type),
            "LLVM_USE_PERF": self.options.use_perf,
            "LLVM_ENABLE_LIBEDIT": self.options.get_safe("with_libedit", False),
            "LLVM_ENABLE_Z3_SOLVER": self.options.with_z3,
            "LLVM_ENABLE_FFI": self.options.with_ffi,
            "LLVM_ENABLE_ZLIB": "FORCE_ON" if self.options.with_zlib else False,
            "LLVM_ENABLE_LIBXML2": "FORCE_ON" if self.options.with_xml2 else False,
        }
        if Version(self.version) < 19:
            cmake_variables["LLVM_ENABLE_TERMINFO"] = self.options.get_safe("with_terminfo")
        else:
            cmake_variables["LLVM_ENABLE_ZSTD"] = "FORCE_ON" if self.options.get_safe("with_zstd") else False

        if self.options.targets != "all":
            cmake_variables["LLVM_TARGETS_TO_BUILD"] = self.options.targets

        self._apply_resource_limits(cmake_variables)

        if is_msvc(self):
            build_type = str(self.settings.build_type).upper()
            cmake_variables[f"LLVM_USE_CRT_{build_type}"] = msvc_runtime_flag(self)

        if not self.options.shared:
            cmake_variables.update({
                "DISABLE_LLVM_LINK_LLVM_DYLIB": True,
                "LLVM_ENABLE_PIC": self.options.get_safe("fPIC", default=True)
            })

        if self.options.use_sanitizer == "None":
            cmake_variables["LLVM_USE_SANITIZER"] = ""
        else:
            cmake_variables["LLVM_USE_SANITIZER"] = self.options.use_sanitizer

        if self.settings.os == "Linux":
            # Workaround for: https://github.com/conan-io/conan/issues/13560
            libdirs_host = [l for dependency in self.dependencies.host.values() for l in dependency.cpp_info.aggregated_components().libdirs]
            tc.variables["CMAKE_BUILD_RPATH"] = ";".join(libdirs_host)

        tc.cache_variables.update(cmake_variables)
        tc.generate()

        deps = CMakeDeps(self)
        deps.generate()

    @property
    def _graphviz_file(self):
        return PurePosixPath(self.build_folder) / "llvm-core.dot"

    def build(self):
        apply_conandata_patches(self)
        cmake = CMake(self)
        graphviz_args = [f"--graphviz={self._graphviz_file}"]

        # components not exported or not of interest
        exclude_patterns = [
            "LLVMTableGenGlobalISel.*",
            "CONAN_LIB.*",
            "LLVMExegesis.*",
            "LLVMCFIVerify.*"
        ]
        graphviz_options = textwrap.dedent(f"""
            set(GRAPHVIZ_EXECUTABLES OFF)
            set(GRAPHVIZ_MODULE_LIBS OFF)
            set(GRAPHVIZ_OBJECT_LIBS OFF)
            set(GRAPHVIZ_IGNORE_TARGETS "{';'.join(exclude_patterns)}")
        """)
        save(self, PurePosixPath(self.build_folder) / "CMakeGraphVizOptions.cmake", graphviz_options)
        if Version(self.version) < 18:
            cmake.configure(cli_args=graphviz_args)
        else:
            cmake.configure(build_script_folder="llvm-main", cli_args=graphviz_args)
        cmake.build()

    @property
    def _package_folder_path(self):
        return PurePosixPath(self.package_folder)

    @property
    def _llvm_source_folder_path(self):
        if (Version(self.version) < 18):
            return PurePosixPath(self.source_folder)

        return PurePosixPath(self.source_folder) / "llvm-main"

    def _llvm_build_info(self):
        cmake_config = Path(self._package_folder_path / "lib" / "cmake" / "llvm" / "LLVMConfig.cmake").read_text("utf-8")
        components = components_from_dotfile(load(self, self._graphviz_file))

        return {
            "components": components,
            "native_arch": re.search(r"""^set\(LLVM_NATIVE_ARCH (\S*)\)$""", cmake_config, re.MULTILINE).group(1)
        }

    @property
    def _cmake_module_path(self):
        return PurePosixPath("lib") / "cmake" / "llvm"

    @property
    def _build_info_file(self):
        return self._package_folder_path / self._cmake_module_path / "conan_llvm_build_info.json"

    @property
    def _build_module_file_rel_path(self):
        return self._cmake_module_path / f"conan-official-{self.name}-variables.cmake"

    def _create_cmake_build_module(self, build_info, module_file):
        targets_with_jit = ["X86", "PowerPC", "AArch64", "ARM", "Mips", "SystemZ"]
        content = textwrap.dedent(f"""\
            set(LLVM_TOOLS_BINARY_DIR "${{CMAKE_CURRENT_LIST_DIR}}/../../../bin")
            cmake_path(NORMAL_PATH LLVM_TOOLS_BINARY_DIR)
            set(LLVM_PACKAGE_VERSION "{self.version}")
            set(LLVM_AVAILABLE_LIBS "{';'.join(build_info['components'].keys())}")
            set(LLVM_BUILD_TYPE "{self.settings.build_type}")
            set(LLVM_CMAKE_DIR "${{CMAKE_CURRENT_LIST_DIR}}")
            list(APPEND CMAKE_MODULE_DIR ${{CMAKE_CURRENT_LIST_DIR}})
            set(LLVM_ALL_TARGETS "{self._all_targets}")
            set(LLVM_TARGETS_TO_BUILD "{self._targets_to_build}")
            set(LLVM_TARGETS_WITH_JIT "{';'.join(targets_with_jit)}")
            set(LLVM_NATIVE_ARCH "{build_info['native_arch']}")
            set_property(GLOBAL PROPERTY LLVM_TARGETS_CONFIGURED On)
            set_property(GLOBAL PROPERTY LLVM_COMPONENT_LIBS ${{LLVM_AVAILABLE_LIBS}})
            if (NOT TARGET intrinsics_gen)
              add_custom_target(intrinsics_gen)
            endif()
            if (NOT TARGET omp_gen)
              add_custom_target(omp_gen)
            endif()
            if (NOT TARGET acc_gen)
              add_custom_target(acc_gen)
            endif()
           """)
        save(self, module_file, content)

    def _write_build_info(self):
        build_info = self._llvm_build_info()
        with open(self._build_info_file, "w", encoding="utf-8") as fp:
            json.dump(build_info, fp, indent=2)

        return build_info

    def _read_build_info(self) -> dict:
        with open(self._build_info_file, encoding="utf-8") as fp:
            return json.load(fp)

    def package(self):
        copy(self, "LICENSE.TXT", self._llvm_source_folder_path, self._package_folder_path / "licenses")
        cmake = CMake(self)
        cmake.install()

        build_info = self._write_build_info()

        cmake_folder = self._package_folder_path / "lib" / "cmake" / "llvm"
        rm(self, "LLVMConfig.cmake", cmake_folder)
        rm(self, "LLVMExports*", cmake_folder)
        rm(self, "Find*", cmake_folder)
        rm(self, "*.pdb", self._package_folder_path / "lib")
        rm(self, "*.pdb", self._package_folder_path / "bin")
        # need to rename this as Conan will flag it, but it's not actually a Config file and is needed by
        # downstream packages
        rename(self, cmake_folder / "LLVM-Config.cmake", cmake_folder / "LLVM-ConfigInternal.cmake")
        replace_in_file(self, cmake_folder / "AddLLVM.cmake", "LLVM-Config", "LLVM-ConfigInternal")
        rmdir(self, self._package_folder_path / "share")
        if self.options.shared:
            rm(self, "*.a", self._package_folder_path / "lib")

        self._create_cmake_build_module(
            build_info,
            self._package_folder_path / self._build_module_file_rel_path
        )

    def package_info(self):
        self.cpp_info.set_property("cmake_file_name", "LLVM")
        self.cpp_info.set_property("cmake_build_modules",
                                   [self._build_module_file_rel_path,
                                    self._cmake_module_path / "LLVM-ConfigInternal.cmake"]
                                   )
        self.cpp_info.builddirs.append(self._cmake_module_path)

        if not self.options.shared:
            build_info = self._read_build_info()
            components = build_info["components"]

            for component_name, data in components.items():
                self.cpp_info.components[component_name].set_property("cmake_target_name", component_name)
                self.cpp_info.components[component_name].libs = [component_name]
                self.cpp_info.components[component_name].requires = data["requires"]
                self.cpp_info.components[component_name].system_libs = data["system_libs"]
        else:
            self.cpp_info.set_property("cmake_target_name", "LLVM")
            self.cpp_info.libs = collect_libs(self)
