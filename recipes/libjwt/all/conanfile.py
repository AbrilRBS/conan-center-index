from conan import ConanFile
from conan.tools.cmake import CMakeToolchain, CMake, cmake_layout, CMakeDeps
from conan.tools.files import get, export_conandata_patches, apply_conandata_patches, rmdir, rename, copy
from conan.tools.gnu import PkgConfigDeps
import os

required_conan_version = ">=2.4"

class libjwtRecipe(ConanFile):
    name = "libjwt"

    # Optional metadata
    license = "Mozilla Public License Version 2.0"
    url = "https://github.com/benmcollins/libjwt"
    description = "The C JSON Web Token Library +JWK +JWKS"
    topics = ("json", "jwt", "jwt-token")

    # Binary configuration
    package_type = "library"
    settings = "os", "compiler", "build_type", "arch"
    options = {
        "shared": [True, False],
        "fPIC": [True, False],
    }
    default_options = {
        "shared": False,
        "fPIC": True,
    }

    implements = ["auto_shared_fpic"]
    languages = "C"

    def export_sources(self):
        export_conandata_patches(self)

    def layout(self):
        cmake_layout(self, src_folder="src")

    def requirements(self):
        self.requires("openssl/[>=3 <4]")
        self.requires("jansson/2.14")

    def source(self):
        get(self, **self.conan_data["sources"][self.version], strip_root=True)
        apply_conandata_patches(self)

    def generate(self):
        deps = CMakeDeps(self)
        deps.generate()

        pkgdeps = PkgConfigDeps(self)
        pkgdeps.generate()

        tc = CMakeToolchain(self)
        # Open an issue if you need support for these!
        tc.cache_variables["WITH_GNUTLS"] = False
        tc.cache_variables["WITH_MBEDTLS"] = False
        # Don't try to build docs even if user has doxygen installed system-wide
        tc.cache_variables["CMAKE_DISABLE_FIND_PACKAGE_Doxygen"] = True
        tc.cache_variables["WITH_TESTS"] = False
        tc.generate()

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE", self.source_folder, dst=os.path.join(self.package_folder, "licenses"))
        cmake = CMake(self)
        cmake.install()
        rmdir(self, os.path.join(self.package_folder, "lib", "pkgconfig"))
        rmdir(self, os.path.join(self.package_folder, "lib", "cmake"))
        rmdir(self, os.path.join(self.package_folder, "share"))

    def package_info(self):
        self.cpp_info.libs = ["jwt"]
        self.cpp_info.set_property("cmake_file_name", "LibJWT")
        self.cpp_info.set_property("cmake_target_name", "LibJWT::jwt")
