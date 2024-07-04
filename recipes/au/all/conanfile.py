from conan import ConanFile
from conan.errors import ConanInvalidConfiguration
from conan.tools.build import check_min_cppstd
from conan.tools.google import bazel_layout, BazelToolchain, BazelDeps, Bazel
from conan.tools.cmake import CMake, CMakeDeps, CMakeToolchain, cmake_layout
from conan.tools.env import VirtualBuildEnv
from conan.tools.files import apply_conandata_patches, copy, export_conandata_patches, get, replace_in_file, rm, rmdir
from conan.tools.layout import basic_layout
from conan.tools.microsoft import check_min_vs, is_msvc, is_msvc_static_runtime
from conan.tools.scm import Version
import os


required_conan_version = ">=1.53.0"


class AuConan(ConanFile):
    name = "au"
    description = "Au is a C++ units library. What the <chrono> library did for time variables, Au does for all physical quantities"
    license = "Apache-2.0"
    url = "https://github.com/conan-io/conan-center-index"
    homepage = "https://github.com/aurora-opensource/au"
    topics = ("units", "quantities", "physical-quantities")
    package_type = "library"
    settings = "os", "arch", "compiler", "build_type"
    # The library provides a header-only alternative, but they only publish for the latest commit,
    # releases do not have them. See https://github.com/aurora-opensource/au/issues/257
    options = {
        "shared": [True, False],
        "fPIC": [True, False],
        # "header_only": [True, False],
    }
    default_options = {
        "shared": False,
        "fPIC": True,
        # "header_only": False
    }

    @property
    def _min_cppstd(self):
        return 14

    @property
    def _compilers_minimum_version(self):
        return {
            "apple-clang": "10",
            "clang": "3",
            "gcc": "5",
            "msvc": "191",
            "Visual Studio": "15",
        }

    def config_options(self):
        if self.settings.os == "Windows":
            del self.options.fPIC

    def configure(self):
        if self.options.shared:
            self.options.rm_safe("fPIC")

    def layout(self):
        bazel_layout(self, src_folder="src")

    def validate(self):
        if self.settings.compiler.cppstd:
            check_min_cppstd(self, self._min_cppstd)
        minimum_version = self._compilers_minimum_version.get(str(self.settings.compiler), False)
        if minimum_version and Version(self.settings.compiler.version) < minimum_version:
            raise ConanInvalidConfiguration(
                f"{self.ref} requires C++{self._min_cppstd}, which your compiler does not support."
            )

    def build_requirements(self):
        self.tool_requires("bazel/[>=6 <7]")

    def source(self):
        get(self, **self.conan_data["sources"][self.version], strip_root=True)

    def generate(self):
        tc = BazelToolchain(self)

        tc.generate()
        deps = BazelDeps(self)
        deps.generate()
        # In case there are dependencies listed on build_requirements, VirtualBuildEnv should be used
        tc = VirtualBuildEnv(self)
        tc.generate(scope="build")

    def build(self):
        bazel = Bazel(self)
        bazel.build()

    def package(self):
        copy(self, "LICENSE.txt", self.source_folder, os.path.join(self.package_folder, "licenses"))

        rm(self, "*.pdb", os.path.join(self.package_folder, "lib"))
        rm(self, "*.pdb", os.path.join(self.package_folder, "bin"))

    def package_info(self):
        self.cpp_info.libs = ["au"]
