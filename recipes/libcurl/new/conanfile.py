from conan import ConanFile
from conan.errors import ConanInvalidConfiguration
from conan.tools.apple import is_apple_os
from conan.tools.cmake import CMake, CMakeToolchain, CMakeDeps, cmake_layout
from conan.tools.files import copy, download, get, replace_in_file, rmdir
from conan.tools.microsoft import is_msvc

import os

required_conan_version = ">=2.28.0"


class LibcurlConan(ConanFile):
    name = "libcurl"
    description = "command line tool and library for transferring data with URLs"
    license = "curl"
    url = "https://github.com/conan-io/conan-center-index"
    homepage = "https://curl.se"
    topics = ("curl", "data-transfer",
            "ftp", "gopher", "http", "imap", "ldap", "mqtt", "pop3", "rtmp", "rtsp",
            "scp", "sftp", "smb", "smtp", "telnet", "tftp")
    package_type = "library"
    settings = "os", "arch", "compiler", "build_type"
    options = {
        "shared": [True, False],
        "fPIC": [True, False],
        "build_executable": [True, False],
        "with_ssl": [False, "openssl", "wolfssl", "schannel", "mbedtls"],
        "with_ldap": [True, False],
        "with_libssh2": [True, False],
        "with_libidn": [True, False],
        "with_libpsl": [True, False],
        "with_largemaxwritesize": [True, False],
        "with_nghttp2": [True, False],
        "with_zlib": [True, False],
        "with_brotli": [True, False],
        "with_zstd": [True, False],
        "with_c_ares": [True, False],
        "with_threaded_resolver": [True, False],
        "with_proxy": [True, False],
        "with_ntlm": [True, False],
        "with_verbose_strings": [True, False],
        "with_ca_bundle": [False, "auto", "ANY"],
        "with_ca_path": [False, "auto", "ANY"],
        "with_ca_fallback": [True, False],
        "with_websockets": [True, False],
        "with_apple_sectrust": [True, False],
    }
    default_options = {
        "shared": False,
        "fPIC": True,
        "build_executable": False,
        "with_ssl": "openssl",
        "with_ldap": False,
        "with_libssh2": False,
        "with_libidn": False,
        "with_libpsl": False,
        "with_largemaxwritesize": False,
        "with_nghttp2": False,
        "with_zlib": True,
        "with_brotli": False,
        "with_zstd": False,
        "with_c_ares": False,
        "with_threaded_resolver": True,
        "with_proxy": True,
        "with_ntlm": False,
        "with_verbose_strings": True,
        "with_ca_bundle": "auto",
        "with_ca_path": "auto",
        "with_ca_fallback": False,
        "with_websockets": True,
        "with_apple_sectrust": False,
    }

    @property
    def _is_mingw(self):
        return self.settings.os == "Windows" and self.settings.compiler == "gcc"

    @property
    def _is_win_x_android(self):
        return self.settings.os == "Android" and self.settings_build.os == "Windows"

    def config_options(self):
        if self.settings.os == "Windows":
            del self.options.fPIC
        if not is_apple_os(self):
            del self.options.with_apple_sectrust

    def configure(self):
        if self.options.shared:
            self.options.rm_safe("fPIC")
        self.settings.rm_safe("compiler.libcxx")
        self.settings.rm_safe("compiler.cppstd")

    def layout(self):
        cmake_layout(self, src_folder="src")

    def requirements(self):
        if self.options.with_ssl == "openssl":
            self.requires(f"openssl/[>=3 <4]")
        elif self.options.with_ssl == "wolfssl":
            self.requires("wolfssl/[>=5.6.6 <6]")
        elif self.options.with_ssl == "mbedtls":
            self.requires("mbedtls/3.5.0")
        if self.settings.os == "Linux" and self.options.with_ldap:
            self.requires("openldap/[>=2.6 <3]")
        if self.options.with_nghttp2:
            self.requires("libnghttp2/[>=1.59.0 <2]")
        if self.options.with_libssh2:
            self.requires("libssh2/[>=1.11.0 <2]")
        if self.options.with_zlib:
            self.requires("zlib/[>=1.2.11 <2]")
        if self.options.with_brotli:
            self.requires("brotli/1.1.0")
        if self.options.with_zstd:
            self.requires("zstd/[~1.5]")
        if self.options.with_c_ares:
            self.requires("c-ares/[>=1.27 <2]")
        if self.options.get_safe("with_libpsl"):
            self.requires("libpsl/0.21.1")
        if self.options.with_libidn:
            self.requires("libidn2/2.3.0")

    def validate(self):
        if self.options.with_ssl == "schannel" and self.settings.os != "Windows":
            raise ConanInvalidConfiguration("schannel only suppported on Windows.")
        if self.options.with_ssl == "openssl":
            openssl = self.dependencies["openssl"]
            if self.options.with_ntlm and openssl.options.no_des:
                raise ConanInvalidConfiguration("option with_ntlm=True requires openssl/*:no_des=False")
        if self.options.with_ssl == "wolfssl":
            wolfssl = self.dependencies["wolfssl"]
            # with_curl alone is not sufficient: curl's wolfssl backend (wolfSSL_CTX_set1_groups_list,
            # used for TLS 1.3 PQC/hybrid key exchange groups) is only compiled into wolfSSL when
            # tls13=True, and several OpenSSL-compat entry points curl also relies on (e.g. MD5) need
            # opensslextra=True. Confirmed empirically: with_curl=True alone fails to link with an
            # undefined wolfSSL_CTX_set1_groups_list; adding tls13=True alone then fails on undefined
            # wc_Md5Final/wc_Md5Update; all three together link and run cleanly.
            if not wolfssl.options.with_curl:
                raise ConanInvalidConfiguration("option with_ssl=wolfssl requires wolfssl/*:with_curl=True")
            if not wolfssl.options.tls13:
                raise ConanInvalidConfiguration("option with_ssl=wolfssl requires wolfssl/*:tls13=True")
            if not wolfssl.options.opensslextra:
                raise ConanInvalidConfiguration("option with_ssl=wolfssl requires wolfssl/*:opensslextra=True")
        if self.options.get_safe("with_apple_sectrust") and self.options.with_ssl != "openssl":
            raise ConanInvalidConfiguration("Apple SecTrust is only supported for OpenSSL/GnuTLS builds")

    def build_requirements(self):
        self.tool_requires("cmake/[>=3.18]")
        if self._is_win_x_android:
            self.tool_requires("ninja/[>=1.10.2 <2]")

    def source(self):
        get(self, **self.conan_data["sources"][self.version], strip_root=True)
        cert_url = self.conf.get("user.libcurl.cert:url", check_type=str) or "https://curl.se/ca/cacert-2025-11-04.pem"
        cert_sha256 = self.conf.get("user.libcurl.cert:sha256", check_type=str) or "8ac40bdd3d3e151a6b4078d2b2029796e8f843e3f86fbf2adbc4dd9f05e79def"
        download(self, cert_url, "cacert.pem", verify=True, sha256=cert_sha256)
        replace_in_file(self, "CMakeLists.txt", "find_package(NGHTTP2 MODULE)", "find_package(NGHTTP2 CONFIG REQUIRED)")
        replace_in_file(self, "CMakeLists.txt", "find_package(Cares MODULE REQUIRED)", "find_package(Cares CONFIG REQUIRED)")
        replace_in_file(self, "CMakeLists.txt", "find_package(Libidn2 MODULE)", "find_package(Libidn2 CONFIG REQUIRED)")
        replace_in_file(self, "CMakeLists.txt", "find_package(Libpsl MODULE REQUIRED)", "find_package(Libpsl CONFIG REQUIRED)")
        replace_in_file(self, "CMakeLists.txt", "find_package(Libssh2 MODULE)", "find_package(Libssh2 CONFIG REQUIRED)")
        # NOT patching MbedTLS to CONFIG REQUIRED (unlike the others above): curl's own bundled
        # CMake/FindMbedTLS.cmake already tries a CONFIG-mode lookup internally (picking up Conan's
        # generated package via the cmake_target_name remap below) before falling back to raw discovery,
        # and crucially it's what sets the uppercase MBEDTLS_VERSION variable CMakeLists.txt checks
        # against a minimum version. Conan's own generated MbedTLSConfig.cmake only defines
        # MbedTLS_VERSION (mixed case), so forcing CONFIG REQUIRED here bypasses curl's own module and
        # breaks that version check outright - confirmed empirically (mbedtls builds cleanly without
        # this patch, fails "mbedTLS v3.2.0 or newer is required" with it).
        replace_in_file(self, "CMakeLists.txt", "find_package(WolfSSL MODULE REQUIRED)", "find_package(WolfSSL CONFIG REQUIRED)")
        # LDAP is only Conan-provided on Linux (see requirements()); Apple/Windows use system LDAP
        # libraries directly via curl's own bundled FindLDAP.cmake raw discovery, which must stay in
        # MODULE mode there. source() can't see settings (sources are shared across configurations),
        # so the choice is deferred to a CMake-level conditional driven by a cache variable set in
        # generate(), instead of branching here.
        replace_in_file(self, "CMakeLists.txt", "find_package(LDAP MODULE)",
                         "if(CURL_RECIPE_LDAP_CONFIG_MODE)\n    find_package(LDAP CONFIG REQUIRED)\n  else()\n    find_package(LDAP MODULE)\n  endif()")
        replace_in_file(self, os.path.join("CMake", "Macros.cmake"), "find_package(${_find_name})", "find_package(${_find_name} CONFIG REQUIRED)")
        replace_in_file(self, os.path.join("CMake", "Macros.cmake"), "find_package(${_find_name} MODULE)", "find_package(${_find_name} CONFIG REQUIRED)")
        replace_in_file(self, os.path.join("CMake", "Macros.cmake"), "find_package(${_find_name} REQUIRED)", "find_package(${_find_name} CONFIG REQUIRED)")
        replace_in_file(self, os.path.join("CMake", "Macros.cmake"), "find_package(${_find_name} MODULE REQUIRED)", "find_package(${_find_name} CONFIG REQUIRED)")

    def generate(self):
        if self._is_win_x_android:
            tc = CMakeToolchain(self, generator="Ninja")
        else:
            tc = CMakeToolchain(self)
        tc.cache_variables["ENABLE_UNICODE"] = True
        tc.cache_variables["BUILD_TESTING"] = False
        tc.cache_variables["BUILD_CURL_EXE"] = self.options.build_executable
        tc.cache_variables["ENABLE_CURL_MANUAL"] = False
        tc.cache_variables["BUILD_LIBCURL_DOCS"] = False
        tc.cache_variables["BUILD_MISC_DOCS"] = False
        tc.cache_variables["CURL_DISABLE_LDAP"] = not self.options.with_ldap
        tc.cache_variables["CURL_RECIPE_LDAP_CONFIG_MODE"] = self.settings.os == "Linux" and bool(self.options.with_ldap)
        tc.cache_variables["BUILD_SHARED_LIBS"] = self.options.shared
        # Curl has -d by default for the debug postfix, but old autotools based logic
        # did not generate any postfix, so disable it everywhere to avoid naming mismatch,
        # even if that means not following upstream naming as we would have desired
        tc.cache_variables["CMAKE_DEBUG_POSTFIX"] = ""
        tc.cache_variables["CURL_USE_SCHANNEL"] = self.options.with_ssl == "schannel"
        tc.cache_variables["CURL_USE_OPENSSL"] = self.options.with_ssl == "openssl"
        tc.cache_variables["CURL_USE_WOLFSSL"] = self.options.with_ssl == "wolfssl"
        tc.cache_variables["CURL_USE_MBEDTLS"] = self.options.with_ssl == "mbedtls"
        tc.cache_variables["USE_NGHTTP2"] = self.options.with_nghttp2
        tc.cache_variables["CURL_ZLIB"] = self.options.with_zlib
        tc.cache_variables["CURL_BROTLI"] = self.options.with_brotli
        tc.cache_variables["CURL_ZSTD"] = self.options.with_zstd
        tc.cache_variables["CURL_USE_LIBPSL"] = self.options.with_libpsl
        tc.cache_variables["CURL_USE_LIBSSH2"] = self.options.with_libssh2
        tc.cache_variables["ENABLE_ARES"] = self.options.with_c_ares
        if not self.options.with_c_ares:
            tc.cache_variables["ENABLE_THREADED_RESOLVER"] = self.options.with_threaded_resolver
        tc.cache_variables["CURL_DISABLE_PROXY"] = not self.options.with_proxy
        tc.cache_variables["USE_LIBIDN2"] = self.options.with_libidn
        if self.options.with_libidn:
            # Conan won't generate this variable as we're setting prefixes,
            # and CMake might not either as it's looking for Libidn2
            # Ensure it's there
            tc.cache_variables["LIBIDN2_FOUND"] = True
        tc.cache_variables["CURL_DISABLE_VERBOSE_STRINGS"] = not self.options.with_verbose_strings
        tc.cache_variables["CURL_DISABLE_WEBSOCKETS"] = not self.options.with_websockets

        # Also disables NTLM_WB if set to false
        tc.cache_variables["CURL_ENABLE_NTLM"] = self.options.with_ntlm

        if self.options.get_safe("with_apple_sectrust"):
            tc.cache_variables["USE_APPLE_SECTRUST"] = True

        if self.options.with_ca_bundle:
            tc.cache_variables["CURL_CA_BUNDLE"] = str(self.options.with_ca_bundle)
        else:
            tc.cache_variables["CURL_CA_BUNDLE"] = "none"

        if self.options.with_ca_path:
            tc.cache_variables["CURL_CA_PATH"] = str(self.options.with_ca_path)
        else:
            tc.cache_variables["CURL_CA_PATH"] = "none"

        tc.cache_variables["CURL_CA_FALLBACK"] = self.options.with_ca_fallback

        # These 3 checks use try_compile() against an imported CMakeDeps target (openssl::openssl), which is
        # fragile across all platforms, not just multi-config generators - see conan-io/conan#12180. The
        # generator-level fix (a rewritten CMakeDeps with proper IMPORTED_CONFIGURATIONS) only ships behind an
        # experimental, not-yet-production-safe conf as of Conan 2.9, and there's a live, still-open upstream
        # CMake regression in the same area (cmake/cmake#27487), so pre-seeding these avoids the try_compile
        # path entirely rather than depending on either fix landing.
        tc.cache_variables["HAVE_SSL_SET0_WBIO"] = False
        tc.cache_variables["HAVE_OPENSSL_SRP"] = True
        tc.cache_variables["HAVE_SSL_CTX_SET_QUIC_METHOD"] = True

        # Recommended general mitigation for the same class of try_compile-with-imported-targets issue
        # (conan-io/conan#12180) for any other feature check curl's CMakeLists.txt performs that isn't
        # pre-seeded above - cheap to set unconditionally, and the original issue reproduced on macOS too,
        # not just MSVC.
        tc.cache_variables["CMAKE_TRY_COMPILE_CONFIGURATION"] = str(self.settings.build_type)

        if self.options.with_libssh2:
            # Not generated automatically
            tc.cache_variables["LIBSSH2_FOUND"] = True

        tc.generate()

        deps = CMakeDeps(self)
        deps.set_property("wolfssl", "cmake_additional_variables_prefixes", ["WolfSSL", "WOLFSSL"])
        deps.set_property("wolfssl", "cmake_file_name", "WolfSSL")

        if self.options.with_brotli:
            deps.set_property("brotli", "cmake_file_name", "Brotli")
            deps.set_property("brotli", "cmake_target_name", "CURL::brotli")
            deps.set_property("brotli", "cmake_additional_variables_prefixes", ["BROTLI",])
            deps.set_property("brotli", "cmake_extra_variables", {"BROTLI_FOUND": "1"})

        if self.options.with_zstd:
            deps.set_property("zstd", "cmake_file_name", "Zstd")
            deps.set_property("zstd", "cmake_target_name", "CURL::zstd")
            deps.set_property("zstd", "cmake_additional_variables_prefixes", ["ZSTD",])
            deps.set_property("zstd", "cmake_extra_variables", {"ZSTD_FOUND": "1", "ZSTD_VERSION": str(self.dependencies["zstd"].ref.version)})

        if self.options.with_c_ares:
            deps.set_property("c-ares", "cmake_file_name", "Cares")
            deps.set_property("c-ares", "cmake_target_name", "CURL::cares")

        if self.settings.os == "Linux" and self.options.with_ldap:
            deps.set_property("openldap", "cmake_file_name", "LDAP")
            deps.set_property("openldap", "cmake_target_name", "CURL::ldap")

        if self.options.with_libidn:
            deps.set_property("libidn2", "cmake_file_name", "Libidn2")
            deps.set_property("libidn2", "cmake_target_name", "CURL::libidn2")
            deps.set_property("libidn2", "cmake_additional_variables_prefixes", ["LIBIDN2"])

        if self.options.get_safe("with_libpsl"):
            deps.set_property("libpsl", "cmake_file_name", "Libpsl")
            deps.set_property("libpsl", "cmake_target_name", "CURL::libpsl")

        if self.options.with_libssh2:
            deps.set_property("libssh2", "cmake_file_name", "Libssh2")
            deps.set_property("libssh2", "cmake_target_name", "CURL::libssh2")

        if self.options.with_nghttp2:
            deps.set_property("libnghttp2", "cmake_file_name", "NGHTTP2")
            deps.set_property("libnghttp2", "cmake_target_name", "CURL::nghttp2")

        if self.options.with_ssl == "wolfssl":
            deps.set_property("wolfssl", "cmake_target_name", "CURL::wolfssl")
        # Now the rest of the dependencies that don't use the imported target directly
        # (openssl, zlib)

        if self.options.with_ssl == "mbedtls":
            deps.set_property("mbedtls", "cmake_target_name", "CURL::mbedtls")

        deps.generate()

    def build(self):
        self._patch_sources()
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def _patch_sources(self):
        if self.options.with_largemaxwritesize:
            replace_in_file(self, os.path.join(self.source_folder, "include", "curl", "curl.h"),
                                  "define CURL_MAX_WRITE_SIZE 16384",
                                  "define CURL_MAX_WRITE_SIZE 10485760")

    def package(self):
        copy(self, "COPYING", src=self.source_folder, dst=os.path.join(self.package_folder, "licenses"))
        copy(self, "cacert.pem", src=self.source_folder, dst=os.path.join(self.package_folder, "res"))
        cmake = CMake(self)
        cmake.install()
        rmdir(self, os.path.join(self.package_folder, "lib", "cmake"))
        rmdir(self, os.path.join(self.package_folder, "lib", "pkgconfig"))
        rmdir(self, os.path.join(self.package_folder, "share"))

    def package_info(self):
        self.cpp_info.set_property("cmake_file_name", "CURL")
        self.cpp_info.set_property("cmake_target_name", "CURL::libcurl")
        self.cpp_info.set_property("cmake_find_mode", "both")
        self.cpp_info.set_property("pkg_config_name", "libcurl")

        self.cpp_info.components["curl"].resdirs = ["res"]
        if is_msvc(self):
            self.cpp_info.components["curl"].libs = ["libcurl_imp"] if self.options.shared else ["libcurl"]
        else:
            self.cpp_info.components["curl"].libs = ["curl"]

        if self.settings.os in ["Linux", "FreeBSD"]:
            self.cpp_info.components["curl"].system_libs = ["rt", "pthread"]
        elif self.settings.os == "Windows":
            # used on Windows for VS build, native and cross mingw build
            self.cpp_info.components["curl"].system_libs = ["ws2_32", "bcrypt", "iphlpapi"]
            if self.options.with_ldap:
                self.cpp_info.components["curl"].system_libs.append("wldap32")
            if self.options.with_ssl == "schannel":
                self.cpp_info.components["curl"].system_libs.extend(["crypt32", "secur32"])
        elif is_apple_os(self):
            self.cpp_info.components["curl"].frameworks.append("CoreFoundation")
            self.cpp_info.components["curl"].frameworks.append("CoreServices")
            self.cpp_info.components["curl"].frameworks.append("SystemConfiguration")
            if self.options.get_safe("with_apple_sectrust"):
                self.cpp_info.components["curl"].frameworks.append("Security")
            if self.options.with_ldap:
                self.cpp_info.components["curl"].system_libs.append("ldap")

        if self._is_mingw:
            # provide pthread for dependent packages
            self.cpp_info.components["curl"].cflags.append("-pthread")
            self.cpp_info.components["curl"].exelinkflags.append("-pthread")
            self.cpp_info.components["curl"].sharedlinkflags.append("-pthread")

        if not self.options.shared:
            self.cpp_info.components["curl"].defines.append("CURL_STATICLIB=1")

        if self.options.with_ssl == "openssl":
            self.cpp_info.components["curl"].requires.append("openssl::openssl")
        if self.options.with_ssl == "wolfssl":
            self.cpp_info.components["curl"].requires.append("wolfssl::wolfssl")
        if self.options.with_ssl == "mbedtls":
            self.cpp_info.components["curl"].requires.append("mbedtls::mbedtls")
        if self.settings.os == "Linux" and self.options.with_ldap:
            self.cpp_info.components["curl"].requires.append("openldap::openldap")
        if self.options.with_nghttp2:
            self.cpp_info.components["curl"].requires.append("libnghttp2::libnghttp2")
        if self.options.with_libssh2:
            self.cpp_info.components["curl"].requires.append("libssh2::libssh2")
        if self.options.with_zlib:
            self.cpp_info.components["curl"].requires.append("zlib::zlib")
        if self.options.with_brotli:
            self.cpp_info.components["curl"].requires.append("brotli::brotli")
        if self.options.with_zstd:
            self.cpp_info.components["curl"].requires.append("zstd::zstd")
        if self.options.with_c_ares:
            self.cpp_info.components["curl"].requires.append("c-ares::c-ares")
        if self.options.get_safe("with_libpsl"):
            self.cpp_info.components["curl"].requires.append("libpsl::libpsl")
        if self.options.with_libidn:
            self.cpp_info.components["curl"].requires.append("libidn2::libidn2")

        self.cpp_info.components["curl"].set_property("cmake_target_name", "CURL::libcurl")
        self.cpp_info.components["curl"].set_property("pkg_config_name", "libcurl")
