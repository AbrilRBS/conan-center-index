from conan import ConanFile
from conan.errors import ConanInvalidConfiguration
from conan.tools.android import android_abi
from conan.tools.build import check_min_cppstd
from conan.tools.cmake import CMake, CMakeDeps, CMakeToolchain, cmake_layout
from conan.tools.env import VirtualBuildEnv
from conan.tools.files import apply_conandata_patches, export_conandata_patches, get, rmdir, save, copy, replace_in_file
from conan.tools.microsoft import is_msvc_static_runtime
import os

required_conan_version = ">=1.53.0"


class SfmlConan(ConanFile):
    name = "sfml"
    description = "Simple and Fast Multimedia Library."
    license = "Zlib"
    url = "https://github.com/conan-io/conan-center-index"
    homepage = "https://www.sfml-dev.org"
    topics = ("multimedia", "games", "graphics", "audio")
    package_type = "library"
    settings = "os", "arch", "compiler", "build_type"
    options = {
        "shared": [True, False],
        "fPIC": [True, False],
        # modules
        "window": [True, False],
        "graphics": [True, False],
        "network": [True, False],
        "audio": [True, False],
        # window module options
        "opengl": ["es", "desktop"],
        "use_drm": [True, False],  # Linux only
        # "use_mesa3d": [True, False],  # Windows only, not available in CCI

    }
    default_options = {
        "shared": False,
        "fPIC": True,
        "window": True,
        "graphics": True,
        "network": True,
        "audio": True,
        "opengl": "desktop",
        "use_drm": False,
        # "use_mesa3d": False,
    }

    @property
    def _min_cppstd(self):
        return 17

    def export_sources(self):
        export_conandata_patches(self)

    def config_options(self):
        if self.settings.os == "Windows":
            del self.options.fPIC
        else:
            pass
            # del self.options.use_mesa3d

        if self.settings.os == "Android":
            del self.options.shared
            del self.options.fPIC
            self.package_type = "shared-library"

    def configure(self):
        if self.options.get_safe("shared"):
            self.options.rm_safe("fPIC")

        if not self.options.window:
            del self.options.opengl
            del self.options.use_drm
        elif self.settings.os != "Linux":
            del self.options.use_drm  # For Window module but only available on Linux

    def layout(self):
        cmake_layout(self, src_folder="src")

    def requirements(self):
        if self.options.window:
            if self.settings.os in ["Linux", "FreeBSD"]:
                if self.options.get_safe("use_drm"):
                    self.requires("libdrm/2.4.120")
                    # TODO
                    # self.requires("libgbm/20.3.0")  # Missing in CCI?
                else:
                    self.requires("xorg/system")
                if self.settings.os == "Linux":
                    self.requires("libudev/system")
                if self.settings.os == "FreeBSD":
                    # TODO: usbhid
                    pass

            if self.settings.os == "Android":
                # TODO: EGL, GLES
                pass
            elif self.settings.os != "iOS":  # Handled as a framework
                self.requires("opengl/system")

        if self.options.graphics:
            if self.settings.os == "Android" or self.settings.os == "iOS":
                self.requires("zlib/[>=1.2.11 <2]")
            if self.settings.os == "iOS":
                self.requires("bzip2/1.0.8")
            self.requires("freetype/2.13.2")

        if self.options.audio:
            self.requires("vorbis/1.3.7")
            self.requires("flac/1.4.3")

    def build_requirements(self):
        self.tool_requires("cmake/[>=3.24 <4]")
        if not self.conf.get("tools.gnu:pkg_config", check_type=str):
            self.tool_requires("pkgconf/[>=2.2 <3]")

    def validate(self):
        if self.options.graphics and not self.options.window:
            raise ConanInvalidConfiguration(f"-o={self.ref}:graphics=True requires -o={self.ref}:window=True")

        if self.options.get_safe("shared") and is_msvc_static_runtime(self):
            raise ConanInvalidConfiguration(f"{self.ref} does not support shared libraries with static runtime")

        if self.settings.compiler.cppstd:
            check_min_cppstd(self, self._min_cppstd)

        if self.settings.os not in ["Windows", "Linux", "FreeBSD", "Android", "Macos", "iOS"]:
            raise ConanInvalidConfiguration(f"{self.ref} not supported on {self.settings.os}")

    def validate_build(self):
        if self.settings.os == "Macos" and self.settings.compiler != "apple-clang":
            raise ConanInvalidConfiguration(f"{self.ref} is not supported on {self.settings.os} with {self.settings.compiler}")

    def source(self):
        get(self, **self.conan_data["sources"][self.version], strip_root=True)

    def generate(self):
        venv = VirtualBuildEnv(self)
        venv.generate()
        tc = CMakeToolchain(self)

        tc.variables["SFML_BUILD_WINDOW"] = self.options.window
        tc.variables["SFML_BUILD_GRAPHICS"] = self.options.graphics
        tc.variables["SFML_BUILD_NETWORK"] = self.options.network
        tc.variables["SFML_BUILD_AUDIO"] = self.options.audio

        if self.options.window:
            tc.variables["SFML_OPENGL_ES"] = True if self.options.opengl == "es" else False

            if self.settings.os == "Linux":
                tc.variables["SFML_USE_DRM"] = self.options.use_drm

        tc.variables["SFML_GENERATE_PDB"] = False  # PDBs not allowed in CCI

        if self.settings.os == "Windows":
            tc.cache_variables["SFML_USE_STATIC_STD_LIBS"] = is_msvc_static_runtime(self)

        tc.cache_variables["SFML_USE_SYSTEM_DEPS"] = True

        if self.settings.os == "Windows":
            tc.cache_variables["SFML_USE_MESA3D"] = False  # self.options.use_mesa3d

        tc.variables["SFML_INSTALL_PKGCONFIG_FILES"] = False
        tc.variables["SFML_CONFIGURE_EXTRAS"] = False

        tc.cache_variables["SFML_WARNINGS_AS_ERRORS"] = False

        # tc.cache_variables["SFML_MISC_INSTALL_PREFIX"] = os.path.join(self.package_folder, "licenses").replace("\\", "/")

        tc.generate()
        deps = CMakeDeps(self)
        deps.set_property("flac", "cmake_file_name", "FLAC")
        deps.generate()

    def _patch_sources(self):
        apply_conandata_patches(self)

    def build(self):
        self._patch_sources()
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "license.md", self.source_folder, os.path.join(self.package_folder, "licenses"))
        cmake = CMake(self)
        cmake.install()

        rmdir(self, os.path.join(self.package_folder, "lib", "cmake"))
        rmdir(self, os.path.join(self.package_folder, "share"))

    def _default_module(self, name):
        libname = f"sfml-{name}"
        if name != "main" and (self.options.get_safe("shared") or self.settings.os == "Android"):
            if self.settings.os == "Windows":
                # TODO: Handle Windows versioning
                pass
            elif self.settings.build_type == "Debug":
                libname += "-d"
        else:
            libname += "-s"
            self.cpp_info.components[name].defines = ["SFML_STATIC"]
            if self.settings.build_type == "Debug":
                libname += "-d"
        self.cpp_info.components[name].libs = [libname]

        if self.settings.os == "Android":
            self.cpp_info.components[name].libdirs = [os.path.join("lib", android_abi(self))]

        # TODO:
        # if(SFML_COMPILER_GCC OR SFML_COMPILER_CLANG)
        #                 # on Windows + gcc/clang get rid of "lib" prefix for shared libraries,
        #                 # and transform the ".dll.a" suffix into ".a" for import libraries
        #                 set_target_properties(${target} PROPERTIES PREFIX "")
        #                 set_target_properties(${target} PROPERTIES IMPORT_SUFFIX ".a")
        #             endif()

    def package_info(self):
        self.cpp_info.set_property("cmake_file_name", "SFML")
        self.cpp_info.set_property("pkg_config_name", "sfml-all")

        # if self.options.get_safe("opengl") == "desktop":
        # -DSFML_OPENGL_ES
        # -DGL_GLEXT_PROTOTYPES

        # TODO: libatomic when gcc for graphics and audio, but only iof not available?
        # code says: (e.g. Raspberry Pi 3 armhf), GCC requires linking libatomic to use <atomic> features

        modules = ["system"]
        if self.settings.os in ["Windows", "iOS", "Android"]:
            modules.append("main")

        modules.extend(module for module in ["window", "graphics", "network", "audio"] if self.options.get_safe(module))

        for module in modules:
            self._default_module(module)
            if hasattr(self, f"_{module}_module"):
                getattr(self, f"_{module}_module")()

        # TODO: to remove in conan v2 once cmake_find_package* & pkg_config generators removed
        self.cpp_info.names["cmake_find_package"] = "SFML"
        self.cpp_info.names["cmake_find_package_multi"] = "SFML"
        self.cpp_info.names["pkgconfig"] = "sfml-all"

    def _system_module(self):
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.cpp_info.components["system"].system_libs = ["pthread", "rt"]
        elif self.settings.os == "Windows":
            self.cpp_info.components["system"].system_libs = ["winmm"]
        elif self.settings.os == "Android":
            # TODO: Android
            self.cpp_info.components["system"].system_libs = ["log"]

    def _window_module(self):
        if self.options.window:
            self.cpp_info.components["window"].requires = ["system"]
            if self.settings.os in ["Linux", "FreeBSD"]:
                self.cpp_info.components["window"].system_libs.append("dl")
                if self.options.get_safe("use_drm"):
                    self.cpp_info.components["window"].requires.append("libdrm::libdrm")
                    # TODO
                    # self.cpp_info.components["window"].requires.append("libgbm::libgbm")
                else:
                    self.cpp_info.components["window"].requires.extend(["xorg::x11", "xorg::xrandr", "xorg::xcursor", "xorg::xi"])

            if self.settings.os == "iOS":
                self.cpp_info.components["window"].frameworks = ["OpenGLES"]
            elif self.settings.os == "Android":
                # TODO: EGL, GLES, this is experimental
                # self.cpp_info.components["window"].system_libs.extend(["egl", "GLESv2"])
                pass
            else:
                self.cpp_info.components["window"].requires.append("opengl::opengl")

            if self.settings.os == "Linux":
                self.cpp_info.components["window"].requires.append("libudev::libudev")
            elif self.settings.os == "Windows":
                self.cpp_info.components["window"].system_libs.extend(["gdi32", "winmm"])
            elif self.settings.os == "FreeBSD":
                # TODO: usbhid
                pass
            elif self.settings.os == "Macos":
                self.cpp_info.components["window"].frameworks = ["Foundation", "AppKit", "IOKit", "Carbon"]
            elif self.settings.os == "iOS":
                self.cpp_info.components["window"].frameworks = ["Foundation", "UIKit", "CoreGraphics", "QuartzCore", "CoreMotion"]
            elif self.settings.os == "Android":
                # TODO: android
                pass

    def _graphics_module(self):
        if self.options.graphics:
            self.cpp_info.components["graphics"].requires = ["window"]
            if self.settings.os == "Android" or self.settings.os == "iOS":
                self.cpp_info.components["graphics"].requires.append("zlib::zlib")
            if self.settings.os == "iOS":
                self.cpp_info.components["graphics"].requires.append("bzip2::bzip2")
            self.cpp_info.components["graphics"].requires.append("freetype::freetype")
            # TODO: Atomic

    def _network_module(self):
        if self.options.network:
            if self.settings.os == "Windows":
                self.cpp_info.components["network"].requires = ["system"]
                self.cpp_info.components["network"].system_libs = ["ws2_32"]

    def _audio_module(self):
        if self.options.audio:
            self.cpp_info.components["audio"].requires = ["vorbis::vorbis", "flac::flac"]
            if self.settings.os == "iOS":
                self.cpp_info.components["audio"].frameworks = ["Foundation", "CoreFoundation", "CoreAudio", "AudioToolbox", "AVFoundation"]
            else:
                self.cpp_info.components["audio"].requires.extend(["vorbis::vorbisfile", "vorbis::vorbisenc"])

            if self.settings.os == "Android":
                # TODO: target_link_libraries(sfml-audio PRIVATE android OpenSLES)
                pass

            if self.settings.os == "Linux":
                self.cpp_info.components["audio"].system_libs = ["dl"]
