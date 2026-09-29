from conan import ConanFile
from conan.errors import ConanException, ConanInvalidConfiguration
from conan.tools.apple import is_apple_os
from conan.tools.build import check_min_cppstd, valid_min_cppstd
from conan.tools.cmake import CMake, CMakeDeps, CMakeToolchain, cmake_layout
from conan.tools.files import apply_conandata_patches, collect_libs, copy, export_conandata_patches, get, rename, replace_in_file, rmdir, save
from conan.tools.gnu import PkgConfigDeps
from conan.tools.microsoft import is_msvc, msvc_runtime_flag
from conan.tools.scm import Version
import os
import re
import textwrap

required_conan_version = ">=2.1"


# OpenCV 5.0 reorganized its module set: calib3d/features2d were split (see
# https://github.com/opencv/opencv/wiki/OpenCV-4-to-5-migration), ml and gapi moved out of the
# main opencv repository into opencv_contrib, and geometry/ptcloud are new, while stereo was
# promoted from opencv_contrib into the main repository.
OPENCV_MAIN_MODULES_OPTIONS = (
    "calib",
    "dnn",
    "features",
    "flann",
    "geometry",
    "highgui",
    "imgcodecs",
    "imgproc",
    "objdetect",
    "photo",
    "ptcloud",
    "stereo",
    "stitching",
    "video",
    "videoio",
)

# Extra modules built from the opencv_contrib source tree. This intentionally excludes many
# modules opencv_contrib ships (alphamat, cvv, dpm, fuzzy, hdf, hfs, img_hash, intensity_transform,
# line_descriptor, ovis, phase_unwrapping, rapid, reg, saliency, shape, structured_light,
# surface_matching, viz, and new-in-5.0 modules with no track record yet such as signal/xstereo):
# none of them are consumed by anything else in this repository, several are explicitly marked
# experimental/unmaintained upstream, and viz in particular can never build here since it requires
# VTK, which isn't packaged in ConanCenter. `ml` and `gapi` are exposed here (default True, see
# below) even though their source now lives under opencv_contrib, since they are default-enabled,
# widely used modules, not optional extras.
OPENCV_EXTRA_MODULES_OPTIONS = (
    "bgsegm",
    "bioinspired",
    "ccalib",
    "cudaarithm",
    "cudabgsegm",
    "cudacodec",
    "cudafeatures2d",
    "cudafilters",
    "cudaimgproc",
    "cudalegacy",
    "cudaobjdetect",
    "cudaoptflow",
    "cudastereo",
    "cudawarping",
    "datasets",
    "dnn_objdetect",
    "dnn_superres",
    "face",
    "freetype",
    "gapi",
    "ml",
    "optflow",
    "plot",
    "quality",
    "rgbd",
    "sfm",
    "superres",
    "text",
    "tracking",
    "videostab",
    "wechat_qrcode",
    "xfeatures2d",
    "ximgproc",
    "xobjdetect",
    "xphoto",
)

class OpenCVConan(ConanFile):
    name = "opencv"
    license = "Apache-2.0"
    homepage = "https://opencv.org"
    description = "OpenCV (Open Source Computer Vision Library)"
    url = "https://github.com/conan-io/conan-center-index"
    topics = ("computer-vision", "deep-learning", "image-processing")

    package_type = "library"
    settings = "os", "arch", "compiler", "build_type"
    options = {
        "shared": [True, False],
        "fPIC": [True, False],
        # global options
        "parallel": [False, "tbb", "openmp"],
        "with_ipp": [False, "intel-ipp", "opencv-icv"],
        "with_eigen": [True, False],
        "with_opencl": [True, False],
        "with_cuda": [True, False],
        "with_cublas": [True, False],
        "with_cufft": [True, False],
        "with_cudnn": [True, False],
        "cuda_arch_bin": [None, "ANY"],
        "cpu_baseline": [None, "ANY"],
        "cpu_dispatch": [None, "ANY"],
        "world": [True, False],
        "nonfree": [True, False],
        # dnn module options
        "with_flatbuffers": [True, False],
        "with_protobuf": [True, False],
        "with_openvino": [True, False],
        "dnn_cuda": [True, False],
        # highgui module options
        "with_gtk": [True, False],
        "with_qt": [True, False],
        "with_wayland": [True, False],
        # imgcodecs module options
        "with_avif": [True, False],
        "with_jpeg": [False, "libjpeg", "libjpeg-turbo", "mozjpeg"],
        "with_png": [True, False],
        "with_tiff": [True, False],
        "with_jpeg2000": [False, "jasper", "openjpeg"],
        "with_openexr": [True, False],
        "with_webp": [True, False],
        "with_imgcodec_gif": [True, False],
        "with_imgcodec_hdr": [True, False],
        "with_imgcodec_pfm": [True, False],
        "with_imgcodec_pxm": [True, False],
        "with_imgcodec_sunraster": [True, False],
        "with_msmf": [True, False],
        "with_msmf_dxva": [True, False],
        # videoio module options
        "with_ffmpeg": [True, False],
        "with_v4l": [True, False],
    }
    options.update({_name: [True, False] for _name in OPENCV_MAIN_MODULES_OPTIONS})
    options.update({_name: [True, False] for _name in OPENCV_EXTRA_MODULES_OPTIONS})

    default_options = {
        "shared": False,
        "fPIC": True,
        # global options
        "parallel": False,
        "with_ipp": False,
        "with_eigen": True,
        "with_opencl": False,
        "with_cuda": False,
        "with_cublas": False,
        "with_cufft": False,
        "with_cudnn": False,
        "cuda_arch_bin": None,
        "cpu_baseline": None,
        "cpu_dispatch": None,
        "world": False,
        "nonfree": False,
        # dnn module options
        "with_flatbuffers": True,
        "with_protobuf": True,
        "with_openvino": False,
        "dnn_cuda": False,
        # highgui module options
        "with_gtk": False,
        "with_qt": False,
        "with_wayland": True,
        # imgcodecs module options
        "with_avif": False,
        "with_jpeg": "libjpeg",
        "with_png": True,
        "with_tiff": True,
        "with_jpeg2000": "openjpeg",
        "with_openexr": True,
        "with_webp": True,
        "with_imgcodec_gif": True,
        "with_imgcodec_hdr": True,
        "with_imgcodec_pfm": True,
        "with_imgcodec_pxm": True,
        "with_imgcodec_sunraster": True,
        "with_msmf": True,
        "with_msmf_dxva": True,
        # videoio module options
        "with_ffmpeg": True,
        "with_v4l": False,
    }
    default_options.update({_name: True for _name in OPENCV_MAIN_MODULES_OPTIONS})
    default_options.update({_name: False for _name in OPENCV_EXTRA_MODULES_OPTIONS})
    # ml and gapi live under opencv_contrib in 5.0 but, unlike the other extra modules above,
    # are default-enabled: they were built by default (as main modules) prior to 5.0, and nothing
    # about the reorganization reduced their real-world usage. xobjdetect now hosts
    # CascadeClassifier/HOGDescriptor (moved out of objdetect in 5.0), so it goes from a niche,
    # never-enabled-by-default extra to a mainstream one.
    default_options.update({"ml": True, "gapi": True, "xobjdetect": True})

    @property
    def _is_cl_like(self):
        return self.settings.compiler.get_safe("runtime") is not None

    @property
    def _is_cl_like_static_runtime(self):
        return self._is_cl_like and "MT" in msvc_runtime_flag(self)

    @property
    def _is_mingw(self):
        return self.settings.os == "Windows" and self.settings.compiler == "gcc"

    @property
    def _contrib_folder(self):
        return os.path.join(self.source_folder, "contrib")

    @property
    def _extra_modules_folder(self):
        return os.path.join(self._contrib_folder, "modules")

    @property
    def _has_with_jpeg2000_option(self):
        return self.settings.os != "iOS"

    @property
    def _has_with_tiff_option(self):
        return self.settings.os != "iOS"

    @property
    def _has_with_ffmpeg_option(self):
        return self.settings.os != "iOS" and self.settings.os != "WindowsStore"

    @property
    def _has_superres_option(self):
        return self.settings.os != "iOS"

    @property
    def _has_with_wayland_option(self):
        return self.settings.os in ["Linux", "FreeBSD"]

    def export_sources(self):
        export_conandata_patches(self)

    def config_options(self):
        if self.settings.os == "Windows":
            del self.options.fPIC
        if self.settings.os != "Linux":
            del self.options.with_gtk
            del self.options.with_v4l
        if self.settings.os in ["iOS", "Android"]:
            del self.options.with_opencl
        if self.settings.os != "Windows":
            del self.options.with_msmf
            del self.options.with_msmf_dxva

        if self._has_with_ffmpeg_option:
            # Following the packager choice, ffmpeg is enabled by default when
            # supported, except on Android. See
            # https://github.com/opencv/opencv/blob/5.0.0/CMakeLists.txt#L211
            self.options.with_ffmpeg = self.settings.os != "Android"
        else:
            del self.options.with_ffmpeg

        if not self._has_with_jpeg2000_option:
            del self.options.with_jpeg2000

        if not self._has_with_tiff_option:
            del self.options.with_tiff
        if not self._has_superres_option:
            del self.options.superres
        if not self._has_with_wayland_option:
            del self.options.with_wayland

        # Conditional default options
        if self._is_mingw:
            # These options are visible for Windows, but upstream disables them
            # by default for MinGW (actually it would fail otherwise)
            self.options.with_msmf = False
            self.options.with_msmf_dxva = False

        if is_msvc(self) and self.settings.arch == "armv8":
            # See https://github.com/opencv/opencv/issues/25052
            #     https://github.com/opencv/opencv/pull/24698#issuecomment-1858023908
            self.options.cpu_baseline = "NEON"
            self.options.cpu_dispatch = ""

    @property
    def _opencv_modules(self):
        def imageformats_deps():
            components = []
            if self.options.get_safe("with_avif"):
                components.append("libavif::libavif")
            if self.options.get_safe("with_jpeg2000"):
                components.append("{0}::{0}".format(self.options.with_jpeg2000))
            if self.options.get_safe("with_png"):
                components.append("libpng::libpng")
            if self.options.get_safe("with_jpeg") == "libjpeg":
                components.append("libjpeg::libjpeg")
            elif self.options.get_safe("with_jpeg") == "libjpeg-turbo":
                components.append("libjpeg-turbo::jpeg")
            elif self.options.get_safe("with_jpeg") == "mozjpeg":
                components.append("mozjpeg::libjpeg")
            if self.options.get_safe("with_tiff"):
                components.append("libtiff::libtiff")
            if self.options.get_safe("with_openexr"):
                components.append("openexr::openexr")
            if self.options.get_safe("with_webp"):
                components.append("libwebp::libwebp")
            return components

        def eigen():
            return ["eigen::eigen"] if self.options.with_eigen else []

        def ffmpeg():
            components = []
            if self.options.get_safe("with_ffmpeg"):
                components = ["ffmpeg::avcodec", "ffmpeg::avformat", "ffmpeg::avutil", "ffmpeg::swscale"]
            return components

        def gtk():
            return ["gtk::gtk"] if self.options.get_safe("with_gtk") else []

        def ipp():
            if self.options.with_ipp == "intel-ipp":
                return ["intel-ipp::intel-ipp"]
            elif self.options.with_ipp == "opencv-icv" and not self.options.shared:
                return ["ippiw"]
            return []

        def parallel():
            return ["onetbb::libtbb"] if self.options.parallel == "tbb" else []

        def protobuf():
            return ["protobuf::protobuf"] if self.options.get_safe("with_protobuf") else []

        def qt():
            return ["qt::qt"] if self.options.get_safe("with_qt") else []

        def wayland():
            return ["wayland::wayland-client", "wayland::wayland-cursor"] if self.options.get_safe("with_wayland") else []

        def xkbcommon():
            return ["xkbcommon::libxkbcommon"] if self.options.get_safe("with_wayland") else []

        def openvino():
            return ["openvino::Runtime"] if self.options.get_safe("with_openvino") else []

        def opencv_calib():
            return ["opencv_calib"] if self.options.calib else []

        def opencv_cudaarithm():
            return ["opencv_cudaarithm"] if self.options.cudaarithm else []

        def opencv_cudacodec():
            return ["opencv_cudacodec"] if self.options.cudacodec else []

        def opencv_cudafeatures2d():
            return ["opencv_cudafeatures2d"] if self.options.cudafeatures2d else []

        def opencv_cudafilters():
            return ["opencv_cudafilters"] if self.options.cudafilters else []

        def opencv_cudaimgproc():
            return ["opencv_cudaimgproc"] if self.options.cudaimgproc else []

        def opencv_cudalegacy():
            return ["opencv_cudalegacy"] if self.options.cudalegacy else []

        def opencv_cudaoptflow():
            return ["opencv_cudaoptflow"] if self.options.cudaoptflow else []

        def opencv_cudawarping():
            return ["opencv_cudawarping"] if self.options.cudawarping else []

        def opencv_datasets():
            return ["opencv_datasets"] if self.options.datasets else []

        def opencv_dnn():
            return ["opencv_dnn"] if self.options.dnn else []

        def opencv_features():
            return ["opencv_features"] if self.options.features else []

        def opencv_flann():
            return ["opencv_flann"] if self.options.flann else []

        def opencv_geometry():
            return ["opencv_geometry"] if self.options.geometry else []

        def opencv_highgui():
            return ["opencv_highgui"] if self.options.highgui else []

        def opencv_imgcodecs():
            return ["opencv_imgcodecs"] if self.options.imgcodecs else []

        def opencv_imgproc():
            return ["opencv_imgproc"] if self.options.imgproc else []

        def opencv_ml():
            return ["opencv_ml"] if self.options.ml else []

        def opencv_objdetect():
            return ["opencv_objdetect"] if self.options.objdetect else []

        def opencv_plot():
            return ["opencv_plot"] if self.options.plot else []

        def opencv_quality():
            return ["opencv_quality"] if self.options.quality else []

        def opencv_stereo():
            return ["opencv_stereo"] if self.options.stereo else []

        def opencv_text():
            return ["opencv_text"] if self.options.text else []

        def opencv_video():
            return ["opencv_video"] if self.options.video else []

        def opencv_videoio():
            return ["opencv_videoio"] if self.options.videoio else []

        def opencv_xfeatures2d():
            return ["opencv_xfeatures2d"] if self.options.xfeatures2d else []

        def opencv_xobjdetect():
            return ["opencv_xobjdetect"] if self.options.xobjdetect else []

        opencv_modules = {
            # Main modules
            "calib": {
                "is_built": self.options.calib,
                "mandatory_options": ["imgproc", "objdetect", "flann", "geometry", "stereo"],
                "requires": ["opencv_imgproc", "opencv_objdetect", "opencv_flann", "opencv_geometry", "opencv_stereo"] + eigen() + ipp(),
            },
            "core": {
                "is_built": True,
                "no_option": True,
                "requires": ["zlib::zlib"] + parallel() + eigen() + ipp(),
                "system_libs": [
                    (self.settings.os == "Android", ["dl", "m", "log"]),
                    (self.settings.os == "FreeBSD", ["m", "pthread"]),
                    (self.settings.os == "Linux", ["dl", "m", "pthread", "rt"]),
                ],
                "frameworks": [
                    (self.settings.os == "Macos" and self.options.get_safe("with_opencl"), ["OpenCL"]),
                ],
            },
            "dnn": {
                "is_built": self.options.dnn,
                "mandatory_options": ["imgproc", "geometry"],
                "requires": ["opencv_core", "opencv_imgproc", "opencv_geometry"] + protobuf() + ipp() + openvino(),
            },
            "features": {
                "is_built": self.options.features,
                "mandatory_options": ["imgproc", "geometry"],
                "requires": ["opencv_imgproc", "opencv_geometry"] + opencv_flann() + opencv_dnn() + eigen() + ipp(),
            },
            "flann": {
                "is_built": self.options.flann,
                "requires": ["opencv_core"] + ipp(),
            },
            "geometry": {
                "is_built": self.options.geometry,
                "mandatory_options": ["flann"],
                "requires": ["opencv_flann"] + eigen() + ipp(),
            },
            "highgui": {
                "is_built": self.options.highgui,
                "mandatory_options": ["imgproc"],
                "requires": ["opencv_imgproc"] + opencv_imgcodecs() +
                            opencv_videoio() + gtk() + qt() + xkbcommon() + wayland() + ipp(),
                "system_libs": [
                    (self.settings.os == "Windows", ["comctl32", "gdi32", "ole32", "setupapi", "ws2_32", "vfw32"]),
                ],
                "frameworks": [
                    (self.settings.os == "Macos", ["Cocoa"]),
                ],
            },
            "imgcodecs": {
                "is_built": self.options.imgcodecs,
                "mandatory_options": ["imgproc"],
                "requires": ["opencv_imgproc", "zlib::zlib"] + imageformats_deps() + ipp(),
                "frameworks": [
                    (is_apple_os(self), ["CoreFoundation", "CoreGraphics"]),
                    (self.settings.os == "iOS", ["UIKit"]),
                    (self.settings.os == "Macos", ["AppKit"]),
                ],
            },
            "imgproc": {
                "is_built": self.options.imgproc,
                "mandatory_options": ["geometry"],
                "requires": ["opencv_core", "opencv_geometry"] + ipp(),
            },
            "objdetect": {
                "is_built": self.options.objdetect,
                "mandatory_options": ["imgproc", "features", "geometry"],
                "requires": ["opencv_core", "opencv_imgproc", "opencv_features", "opencv_geometry"] + opencv_dnn() + ipp(),
            },
            "photo": {
                "is_built": self.options.photo,
                "mandatory_options": ["imgproc", "geometry"],
                "requires": ["opencv_imgproc", "opencv_geometry"] + opencv_cudaarithm() + opencv_cudaimgproc() + ipp(),
            },
            "ptcloud": {
                "is_built": self.options.ptcloud,
                "mandatory_options": ["geometry", "imgproc", "flann"],
                "requires": ["opencv_geometry", "opencv_imgproc", "opencv_flann"] + ipp(),
            },
            "stereo": {
                "is_built": self.options.stereo,
                "mandatory_options": ["imgproc", "geometry"],
                "requires": ["opencv_imgproc", "opencv_geometry"] + ipp(),
            },
            "stitching": {
                "is_built": self.options.stitching,
                "mandatory_options": ["imgproc", "features", "geometry", "flann"],
                "requires": ["opencv_imgproc", "opencv_features", "opencv_geometry", "opencv_flann"] +
                            opencv_xfeatures2d() + opencv_cudaarithm() + opencv_cudawarping() +
                            opencv_cudafeatures2d() + opencv_cudalegacy() + opencv_cudaimgproc() + eigen() + ipp(),
            },
            "video": {
                "is_built": self.options.video,
                "mandatory_options": ["imgproc"],
                "requires": ["opencv_imgproc"] + opencv_geometry() + opencv_features() + opencv_dnn() + ipp(),
            },
            "videoio": {
                "is_built": self.options.videoio,
                "mandatory_options": ["imgcodecs", "imgproc"],
                "requires": ["opencv_imgcodecs", "opencv_imgproc"] + ffmpeg() + ipp(),
                "system_libs": [
                    (self.settings.os == "Android" and int(str(self.settings.os.api_level)) > 20, ["mediandk"]),
                ],
                "frameworks": [
                    (is_apple_os(self), ["Accelerate", "AVFoundation", "CoreGraphics", "CoreMedia", "CoreVideo", "QuartzCore"]),
                    (self.settings.os == "iOS", ["CoreImage", "UIKit"]),
                    (self.settings.os == "Macos", ["Cocoa"]),
                ],
            },
            # Extra modules
            "bgsegm": {
                "is_built": self.options.bgsegm,
                "mandatory_options": ["imgproc", "video", "geometry"],
                "requires": ["opencv_core", "opencv_imgproc", "opencv_video", "opencv_geometry"] + ipp(),
            },
            "bioinspired": {
                "is_built": self.options.bioinspired,
                "requires": ["opencv_core"] + opencv_highgui() + ipp(),
            },
            "ccalib": {
                "is_built": self.options.ccalib,
                "mandatory_options": ["imgproc", "geometry", "calib", "objdetect", "features", "xfeatures2d", "highgui", "imgcodecs"],
                "requires": ["opencv_core", "opencv_imgproc", "opencv_geometry", "opencv_calib", "opencv_objdetect",
                             "opencv_features", "opencv_xfeatures2d", "opencv_highgui", "opencv_imgcodecs"] + ipp(),
            },
            "cudaarithm": {
                "is_built": self.options.cudaarithm,
                "mandatory_options": ["with_cuda"],
                "requires": ["opencv_core", "opencv_cudev"] + ipp(),
            },
            "cudabgsegm": {
                "is_built": self.options.cudabgsegm,
                "mandatory_options": ["with_cuda", "video"],
                "requires": ["opencv_video"] + ipp(),
            },
            "cudacodec": {
                "is_built": self.options.cudacodec,
                "mandatory_options": ["with_cuda", "videoio", "cudaarithm", "cudawarping"],
                "requires": ["opencv_core", "opencv_videoio", "opencv_cudaarithm", "opencv_cudawarping"] + ipp(),
            },
            "cudafeatures2d": {
                "is_built": self.options.cudafeatures2d,
                "mandatory_options": ["with_cuda", "features", "cudafilters", "cudawarping"],
                "requires": ["opencv_features", "opencv_cudafilters", "opencv_cudawarping"] + ipp(),
            },
            "cudafilters": {
                "is_built": self.options.cudafilters,
                "mandatory_options": ["with_cuda", "imgproc", "cudaarithm"],
                "requires": ["opencv_imgproc", "opencv_cudaarithm"] + ipp(),
            },
            "cudaimgproc": {
                "is_built": self.options.cudaimgproc,
                "mandatory_options": ["with_cuda", "imgproc"],
                "requires": ["opencv_imgproc", "opencv_cudev"] + opencv_cudaarithm() + opencv_cudafilters() + opencv_geometry() + ipp(),
            },
            "cudalegacy": {
                "is_built": self.options.cudalegacy,
                "mandatory_options": ["with_cuda", "geometry", "video"],
                "requires": ["opencv_core", "opencv_geometry", "opencv_video"] + opencv_objdetect() + opencv_xobjdetect() +
                            opencv_imgproc() + opencv_stereo() + opencv_calib() +
                            opencv_cudaarithm() + opencv_cudafilters() + opencv_cudaimgproc() + ipp(),
            },
            "cudaobjdetect": {
                "is_built": self.options.cudaobjdetect,
                "mandatory_options": ["with_cuda", "objdetect", "xobjdetect", "cudaarithm", "cudawarping"],
                "requires": ["opencv_objdetect", "opencv_xobjdetect", "opencv_cudaarithm", "opencv_cudawarping"] + opencv_cudalegacy() + ipp(),
            },
            "cudaoptflow": {
                "is_built": self.options.cudaoptflow,
                "mandatory_options": ["with_cuda", "video", "optflow", "cudaarithm", "cudawarping", "cudaimgproc", "cudafeatures2d"],
                "requires": ["opencv_video", "opencv_optflow", "opencv_cudaarithm", "opencv_cudawarping", "opencv_cudaimgproc",
                             "opencv_cudafeatures2d"] + opencv_cudalegacy() + ipp(),
            },
            "cudastereo": {
                "is_built": self.options.cudastereo,
                "mandatory_options": ["with_cuda", "geometry", "stereo"],
                "requires": ["opencv_geometry", "opencv_stereo", "opencv_cudev"] + ipp(),
            },
            "cudawarping": {
                "is_built": self.options.cudawarping,
                "mandatory_options": ["with_cuda", "imgproc", "geometry"],
                "requires": ["opencv_core", "opencv_imgproc", "opencv_geometry", "opencv_cudev"] + ipp(),
            },
            "cudev": {
                "is_built": self.options.with_cuda,
                "no_option": True,
                "requires": ipp(),
            },
            "datasets": {
                "is_built": self.options.datasets,
                "mandatory_options": ["imgcodecs", "ml", "flann"],
                "requires": ["opencv_core", "opencv_imgcodecs", "opencv_ml", "opencv_flann"] + opencv_text() + ipp(),
            },
            "dnn_objdetect": {
                "is_built": self.options.dnn_objdetect,
                "mandatory_options": ["imgproc", "dnn"],
                "requires": ["opencv_core", "opencv_imgproc", "opencv_dnn"] + ipp(),
            },
            "dnn_superres": {
                "is_built": self.options.dnn_superres,
                "mandatory_options": ["imgproc", "dnn"],
                "requires": ["opencv_core", "opencv_imgproc", "opencv_dnn"] + opencv_quality() + ipp(),
            },
            "face": {
                "is_built": self.options.face,
                "mandatory_options": ["imgproc", "xobjdetect", "geometry", "photo"],
                "requires": ["opencv_core", "opencv_imgproc", "opencv_xobjdetect", "opencv_geometry", "opencv_photo"] + ipp(),
            },
            "freetype": {
                "is_built": self.options.freetype,
                "mandatory_options": ["imgproc"],
                "requires": ["opencv_core", "opencv_imgproc", "freetype::freetype", "harfbuzz::harfbuzz"] + ipp(),
            },
            "gapi": {
                "is_built": self.options.gapi,
                "mandatory_options": ["imgproc"],
                "requires": ["opencv_imgproc", "ade::ade"] + opencv_video() + opencv_stereo() + openvino(),
                "system_libs": [
                    (self.settings.os == "Windows", ["ws2_32", "wsock32"]),
                ],
            },
            "ml": {
                "is_built": self.options.ml,
                "mandatory_options": ["geometry"],
                "requires": ["opencv_core", "opencv_geometry"] + ipp(),
            },
            "optflow": {
                "is_built": self.options.optflow,
                "mandatory_options": ["imgproc", "features", "geometry", "video", "ximgproc", "imgcodecs", "flann"],
                "requires": ["opencv_core", "opencv_imgproc", "opencv_features", "opencv_geometry", "opencv_video",
                             "opencv_ximgproc", "opencv_imgcodecs", "opencv_flann"] + ipp(),
            },
            "plot": {
                "is_built": self.options.plot,
                "mandatory_options": ["imgproc"],
                "requires": ["opencv_core", "opencv_imgproc"] + ipp(),
            },
            "quality": {
                "is_built": self.options.quality,
                "mandatory_options": ["imgproc", "ml"],
                "requires": ["opencv_core", "opencv_imgproc", "opencv_ml"] + ipp(),
            },
            "rgbd": {
                "is_built": self.options.rgbd,
                "mandatory_options": ["geometry", "imgproc", "ptcloud"],
                "requires": ["opencv_core", "opencv_geometry", "opencv_imgproc", "opencv_ptcloud"] + ipp(),
            },
            "sfm": {
                "is_built": self.options.sfm,
                "is_part_of_world": False,
                "mandatory_options": ["with_eigen", "geometry", "features", "xfeatures2d", "imgcodecs"],
                "requires": ["opencv_core", "opencv_geometry", "opencv_features", "opencv_xfeatures2d", "opencv_imgcodecs",
                             "opencv.sfm.correspondence", "opencv.sfm.multiview", "opencv.sfm.numeric",
                             "glog::glog", "gflags::gflags"] + eigen() + ipp(),
            },
            "superres": {
                "is_built": self.options.get_safe("superres"),
                "mandatory_options": ["imgproc", "video", "optflow"],
                "requires": ["opencv_imgproc", "opencv_video", "opencv_optflow"] + opencv_videoio() + ipp() +
                            opencv_cudaarithm() + opencv_cudafilters() + opencv_cudawarping() + opencv_cudaimgproc() +
                            opencv_cudaoptflow() + opencv_cudacodec(),
            },
            "text": {
                "is_built": self.options.text,
                "mandatory_options": ["ml", "imgproc", "features", "geometry", "dnn"],
                "requires": ["opencv_core", "opencv_ml", "opencv_imgproc", "opencv_features", "opencv_geometry",
                             "opencv_dnn"] + ipp(),
            },
            "tracking": {
                "is_built": self.options.tracking,
                "mandatory_options": ["imgproc", "video"],
                "requires": ["opencv_core", "opencv_imgproc", "opencv_video"] + opencv_plot() + opencv_dnn() +
                            opencv_datasets() + opencv_highgui() + ipp(),
            },
            "videostab": {
                "is_built": self.options.videostab,
                "mandatory_options": ["imgproc", "features", "video", "photo", "geometry"],
                "requires": ["opencv_imgproc", "opencv_features", "opencv_video", "opencv_photo", "opencv_geometry"] +
                            opencv_videoio() + ipp() + opencv_cudafeatures2d() + opencv_cudawarping() + opencv_cudaoptflow(),
            },
            "wechat_qrcode": {
                "is_built": self.options.wechat_qrcode,
                "mandatory_options": ["geometry", "imgproc", "objdetect", "dnn"],
                "requires": ["opencv_core", "opencv_geometry", "opencv_imgproc", "opencv_objdetect", "opencv_dnn"] + ipp(),
            },
            "xfeatures2d": {
                "is_built": self.options.xfeatures2d,
                "mandatory_options": ["imgproc", "features", "geometry"],
                "requires": ["opencv_core", "opencv_imgproc", "opencv_features", "opencv_geometry"] +
                            opencv_ml() + opencv_cudaarithm() + ipp(),
            },
            "ximgproc": {
                "is_built": self.options.ximgproc,
                "mandatory_options": ["imgproc", "geometry", "stereo", "imgcodecs", "video"],
                "requires": ["opencv_core", "opencv_imgproc", "opencv_geometry", "opencv_stereo", "opencv_imgcodecs",
                             "opencv_video"] + eigen() + ipp(),
            },
            "xobjdetect": {
                "is_built": self.options.xobjdetect,
                "mandatory_options": ["imgproc", "imgcodecs", "features"],
                "requires": ["opencv_core", "opencv_imgproc", "opencv_imgcodecs", "opencv_features"] + ipp(),
            },
            "xphoto": {
                "is_built": self.options.xphoto,
                "mandatory_options": ["imgproc", "photo"],
                "requires": ["opencv_core", "opencv_imgproc", "opencv_photo"] + ipp(),
            },
            # Extra targets (without prefix in their target & lib name)
            "ippiw": {
                "is_built": self.options.with_ipp == "opencv-icv" and not self.options.shared,
                "is_part_of_world": False,
                "no_option": True,
            },
            "opencv.sfm.numeric": {
                "is_built": self.options.sfm,
                "is_part_of_world": False,
                "no_option": True,
                "requires": eigen() + ipp(),
            },
            "opencv.sfm.correspondence": {
                "is_built": self.options.sfm,
                "is_part_of_world": False,
                "no_option": True,
                "requires": ["opencv_imgcodecs", "opencv.sfm.multiview", "glog::glog"] + eigen() + ipp(),
            },
            "opencv.sfm.multiview": {
                "is_built": self.options.sfm,
                "is_part_of_world": False,
                "no_option": True,
                "requires": ["opencv.sfm.numeric", "glog::glog"] + eigen() + ipp(),
            },
        }

        return opencv_modules

    def _get_mandatory_disabled_options(self, opencv_modules):
        direct_options_to_enable = {}
        transitive_options_to_enable = {}

        # Check which direct options have to be enabled
        base_options = [option for option, values in opencv_modules.items()
                        if not values.get("no_option") and self.options.get_safe(option)]
        for base_option in base_options:
            for mandatory_option in opencv_modules.get(base_option, {}).get("mandatory_options", []):
                if not self.options.get_safe(mandatory_option):
                    direct_options_to_enable.setdefault(mandatory_option, set()).add(base_option)

        # Now traverse the graph to check which transitive options have to be enabled
        def collect_transitive_options(base_option, option):
            for mandatory_option in opencv_modules.get(option, {}).get("mandatory_options", []):
                if not self.options.get_safe(mandatory_option):
                    if mandatory_option not in transitive_options_to_enable:
                        transitive_options_to_enable[mandatory_option] = set()
                        collect_transitive_options(base_option, mandatory_option)
                    if base_option not in direct_options_to_enable.get(mandatory_option, set()):
                        transitive_options_to_enable[mandatory_option].add(base_option)

        for base_option in base_options:
            collect_transitive_options(base_option, base_option)

        return {
            "direct": direct_options_to_enable,
            "transitive": transitive_options_to_enable,
        }

    def _solve_internal_dependency_graph(self, opencv_modules):
        disabled_options = self._get_mandatory_disabled_options(opencv_modules)
        direct_options_to_enable = disabled_options["direct"]
        transitive_options_to_enable = disabled_options["transitive"]

        # Enable mandatory options
        all_options_to_enable = set(direct_options_to_enable.keys())
        all_options_to_enable.update(transitive_options_to_enable.keys())
        if all_options_to_enable:
            message = ("Several opencv options which were disabled will be enabled because "
                       "they are required by modules you have explicitly requested:\n")

            for option_to_enable in all_options_to_enable:
                try:
                    setattr(self.options, option_to_enable, True)
                except ConanException:
                    # It may not work in conan v2 and raise ConanException "Incorrect attempt to modify option"
                    continue

                direct_and_transitive = []
                direct = ", ".join(direct_options_to_enable.get(option_to_enable, []))
                if direct:
                    direct_and_transitive.append(f"direct dependency of {direct}")
                transitive = ", ".join(transitive_options_to_enable.get(option_to_enable, []))
                if transitive:
                    direct_and_transitive.append(f"transitive dependency of {transitive}")
                message += f"  - {option_to_enable}: {' / '.join(direct_and_transitive)}\n"

            self.output.warning(message)

    def configure(self):
        if self.options.shared:
            self.options.rm_safe("fPIC")

        # Call this first before any further manipulation of options based on other options
        self._solve_internal_dependency_graph(self._opencv_modules)

        if not (self.options.gapi or self.options.dnn):
            self.options.rm_safe("with_openvino")

        if not self.options.dnn:
            self.options.rm_safe("dnn_cuda")
            self.options.rm_safe("with_flatbuffers")
            self.options.rm_safe("with_protobuf")
        if not self.options.highgui:
            self.options.rm_safe("with_gtk")
            self.options.rm_safe("with_wayland")
            self.options.rm_safe("with_qt")
        if not self.options.imgcodecs:
            self.options.rm_safe("with_avif")
            self.options.rm_safe("with_jpeg")
            self.options.rm_safe("with_jpeg2000")
            self.options.rm_safe("with_openexr")
            self.options.rm_safe("with_png")
            self.options.rm_safe("with_tiff")
            self.options.rm_safe("with_webp")
            self.options.rm_safe("with_imgcodec_gif")
            self.options.rm_safe("with_imgcodec_hdr")
            self.options.rm_safe("with_imgcodec_pfm")
            self.options.rm_safe("with_imgcodec_pxm")
            self.options.rm_safe("with_imgcodec_sunraster")
            self.options.rm_safe("with_msmf")
            self.options.rm_safe("with_msmf_dxva")
        if not self.options.videoio:
            self.options.rm_safe("with_ffmpeg")
            self.options.rm_safe("with_v4l")
        if not self.options.with_cuda:
            self.options.rm_safe("with_cublas")
            self.options.rm_safe("with_cudnn")
            self.options.rm_safe("with_cufft")
            self.options.rm_safe("dnn_cuda")
            self.options.rm_safe("cuda_arch_bin")

        if bool(self.options.get_safe("with_jpeg", False)):
            if self.options.get_safe("with_jpeg2000") == "jasper":
                self.options["jasper"].with_libjpeg = self.options.with_jpeg
            if self.options.get_safe("with_tiff"):
                self.options["libtiff"].jpeg = self.options.with_jpeg

    def layout(self):
        cmake_layout(self, src_folder="src")

    def requirements(self):
        # core module dependencies
        self.requires("zlib/[>=1.2.11 <2]")
        if self.options.with_eigen:
            self.requires("eigen/[>=3.4.0 <4]")
        if self.options.parallel == "tbb":
            self.requires("onetbb/[>=2021.10.0 <2024]")
        if self.options.with_ipp == "intel-ipp":
            self.requires("intel-ipp/2020")
        # dnn module dependencies
        if self.options.get_safe("with_openvino"):
            self.requires("openvino/[>=2024.5.0 <2027]")
        if self.options.get_safe("with_protobuf"):
            # Symbols are exposed https://github.com/conan-io/conan-center-index/pull/16678#issuecomment-1507811867
            # Openvino can lower the protobuf version requirement ceiling to <7 if enabled
            self.requires("protobuf/[>=3.21.12 <8]", transitive_libs=True)
        # gapi module dependencies
        if self.options.gapi:
            self.requires("ade/0.1.2d")
        # highgui module dependencies
        if self.options.get_safe("with_gtk"):
            self.requires("gtk/[>=3.24.51 <4]")
        if self.options.get_safe("with_qt"):
            self.requires("qt/[>=5.15.2 <6]")
        if self.options.get_safe("with_wayland"):
            self.requires("xkbcommon/[>=1.6.0 <2]")
            self.requires("wayland/[>=1.22.0 <2]")
        # imgcodecs module dependencies
        if self.options.get_safe("with_avif"):
            self.requires("libavif/[>=1.0.4 <2]")
        if self.options.get_safe("with_jpeg") == "libjpeg":
            self.requires("libjpeg/[>=9e]")
        elif self.options.get_safe("with_jpeg") == "libjpeg-turbo":
            self.requires("libjpeg-turbo/[>=3.0.2 <4]")
        elif self.options.get_safe("with_jpeg") == "mozjpeg":
            self.requires("mozjpeg/[>=4.1.5 <5]")
        if self.options.get_safe("with_jpeg2000") == "jasper":
            self.requires("jasper/[>=4.2.0 <5]")
        elif self.options.get_safe("with_jpeg2000") == "openjpeg":
            self.requires("openjpeg/[>=2.5.2 <5]")
        if self.options.get_safe("with_png"):
            self.requires("libpng/[>=1.6 <2]")
        if self.options.get_safe("with_openexr"):
            self.requires("openexr/[>=3.2.3 <4]")
        if self.options.get_safe("with_tiff"):
            self.requires("libtiff/[>=4.6.0 <5]")
        if self.options.get_safe("with_webp"):
            self.requires("libwebp/[>=1.3.2 <5]")
        # videoio module dependencies
        if self.options.get_safe("with_ffmpeg"):
            self.requires("ffmpeg/[>=4.4.4 <8]")
        # freetype module dependencies
        if self.options.freetype:
            self.requires("freetype/[>=2.13.2 <3]")
            self.requires("harfbuzz/[>=8.3.0]")
        # sfm module dependencies
        if self.options.sfm:
            self.requires("gflags/[>=2.2.2 <3]")
            self.requires("glog/[>=0.7.0 <1]")

    def _check_mandatory_options(self, opencv_modules):
        disabled_options = self._get_mandatory_disabled_options(opencv_modules)
        direct_disabled_mandatory_options = disabled_options["direct"]
        transitive_disabled_mandatory_options = disabled_options["transitive"]

        # check mandatory options
        all_disabled_mandatory_options = set(direct_disabled_mandatory_options.keys())
        all_disabled_mandatory_options.update(transitive_disabled_mandatory_options.keys())
        if all_disabled_mandatory_options:
            message = ("Several opencv options are disabled but are required by modules "
                       "you have explicitly requested:\n")

            for disabled_option in all_disabled_mandatory_options:
                direct_and_transitive = []
                direct = ", ".join(direct_disabled_mandatory_options.get(disabled_option, []))
                if direct:
                    direct_and_transitive.append(f"direct dependency of {direct}")
                transitive = ", ".join(transitive_disabled_mandatory_options.get(disabled_option, []))
                if transitive:
                    direct_and_transitive.append(f"transitive dependency of {transitive}")
                message += f"  - {disabled_option}: {' / '.join(direct_and_transitive)}\n"

            raise ConanInvalidConfiguration(message)

    def validate(self):
        self._check_mandatory_options(self._opencv_modules)
        # OpenCV 5.0 requires C++17 as a minimum, see
        # https://github.com/opencv/opencv/wiki/OpenCV-4-to-5-migration
        check_min_cppstd(self, 17)
        if self.settings.compiler == "gcc" and Version(self.settings.compiler.version) < "8":
            raise ConanInvalidConfiguration("OpenCV 5.x requires GCC >= 8.")
        if self.settings.compiler == "clang" and Version(self.settings.compiler.version) < "9":
            raise ConanInvalidConfiguration("OpenCV 5.x requires Clang >= 9.")
        if self.options.shared and self._is_cl_like and self._is_cl_like_static_runtime:
            raise ConanInvalidConfiguration("MSVC or clang-cl with static runtime are not supported for shared library.")
        if self.options.get_safe("dnn_cuda") and \
            (not self.options.with_cuda or not self.options.with_cublas or not self.options.with_cudnn):
            raise ConanInvalidConfiguration("with_cublas and with_cudnn must be enabled for dnn_cuda")
        if self.options.with_ipp == "opencv-icv" and \
           not (self.settings.arch in ["x86", "x86_64"] and self.settings.os in ["Linux", "Macos", "Windows"]):
            raise ConanInvalidConfiguration(f"opencv-icv is not available for {self.settings.os}/{self.settings.arch}")

    def build_requirements(self):
        if self.options.get_safe("with_protobuf"):
            self.tool_requires("protobuf/<host_version>")
        if self.options.get_safe("with_wayland"):
            self.tool_requires("wayland-protocols/[>=1.33 <2]")
            self.tool_requires("wayland/<host_version>")
            if not self.conf.get("tools.gnu:pkg_config", check_type=str):
                self.tool_requires("pkgconf/[>=2.1.0 <3]")

    def source(self):
        get(self, **self.conan_data["sources"][self.version][0], strip_root=True)

        get(self, **self.conan_data["sources"][self.version][1],
            destination=self._contrib_folder, strip_root=True)

    def _patch_sources(self):
        apply_conandata_patches(self)

        # Patches in opencv
        # -----------------

        ## Remove 3rd party libs
        for directory in [
            "libjasper", "libjpeg-turbo", "libpng", "libspng", "libtiff",
            "libwebp", "openjpeg", "protobuf", "tbb", "zlib", "zlib-ng",
        ]:
            rmdir(self, os.path.join(self.source_folder, "3rdparty", directory))

        replace_in_file(self, os.path.join(self.source_folder, "CMakeLists.txt"), "ANDROID OR NOT UNIX", "FALSE")
        replace_in_file(self, os.path.join(self.source_folder, "CMakeLists.txt"), "elseif(EMSCRIPTEN)", "elseif(QNXNTO)\nelseif(EMSCRIPTEN)")

        ## Fix link to several dependencies
        replace_in_file(self, os.path.join(self.source_folder, "modules", "imgcodecs", "CMakeLists.txt"), "JASPER_", "Jasper_")
        replace_in_file(self, os.path.join(self.source_folder, "modules", "imgcodecs", "CMakeLists.txt"), "${AVIF_LIBRARY}", "avif")

        ## Fix detection of ffmpeg
        replace_in_file(self, os.path.join(self.source_folder, "modules", "videoio", "cmake", "detect_ffmpeg.cmake"),
                        "FFMPEG_FOUND", "ffmpeg_FOUND")

        ## Robust handling of wayland
        if self.options.get_safe("with_wayland"):
            detect_wayland = os.path.join(self.source_folder, "modules", "highgui", "cmake", "detect_wayland.cmake")

            # We have to override *_LINK_LIBRARIES variables linked to highui because they are just link fkags, not cflags
            # so include dirs are missing (OpenCV seems to assume system libs for wayland)
            replace_in_file(
                self,
                detect_wayland,
                "ocv_check_modules(WAYLAND_CLIENT wayland-client)",
                "ocv_check_modules(WAYLAND_CLIENT wayland-client)\nfind_package(wayland REQUIRED CONFIG)\nset(WAYLAND_CLIENT_LINK_LIBRARIES wayland::wayland-client)",
            )
            replace_in_file(
                self,
                detect_wayland,
                "ocv_check_modules(WAYLAND_CURSOR wayland-cursor)",
                "ocv_check_modules(WAYLAND_CURSOR wayland-cursor)\nset(WAYLAND_CURSOR_LINK_LIBRARIES wayland::wayland-cursor)",
            )
            replace_in_file(
                self,
                detect_wayland,
                "ocv_check_modules(XKBCOMMON xkbcommon)",
                "ocv_check_modules(XKBCOMMON xkbcommon)\nfind_package(xkbcommon REQUIRED CONFIG)\nset(XKBCOMMON_LINK_LIBRARIES xkbcommon::libxkbcommon)",
            )

        ## Cleanup RPATH
        install_layout_file = os.path.join(self.source_folder, "cmake", "OpenCVInstallLayout.cmake")
        replace_in_file(self, install_layout_file,
                              "ocv_update(CMAKE_INSTALL_RPATH \"${CMAKE_INSTALL_PREFIX}/${OPENCV_LIB_INSTALL_PATH}\")",
                              "")
        replace_in_file(self, install_layout_file, "set(CMAKE_INSTALL_RPATH_USE_LINK_PATH TRUE)", "")

        ## Fix discovery & link of protobuf
        if self.options.get_safe("with_protobuf"):
            find_protobuf = os.path.join(self.source_folder, "cmake", "OpenCVFindProtobuf.cmake")
            # OpenCV expects to find FindProtobuf.cmake, not the config file
            replace_in_file(self, find_protobuf,
                            "find_package(Protobuf QUIET)",
                            "find_package(Protobuf REQUIRED MODULE)")
            # in 'if' block, get_target_property() produces an error
            replace_in_file(self, find_protobuf,
                                    'if(TARGET "${Protobuf_LIBRARIES}")',
                                    'if(FALSE)  # patch: disable if(TARGET "${Protobuf_LIBRARIES}")')

        # Patches in opencv_contrib
        # -------------------------

        ## Remove unused extra modules to avoid side effects
        if not self.options.with_cuda:
            rmdir(self, os.path.join(self._extra_modules_folder, "cudev"))
        for module in OPENCV_EXTRA_MODULES_OPTIONS:
            if not self.options.get_safe(module):
                rmdir(self, os.path.join(self._extra_modules_folder, module))
        for module in [
            "alphamat", "cannops", "cnn_3dobj", "cvv", "dnns_easily_fooled", "dpm", "fastcv", "fuzzy",
            "hdf", "hfs", "img_hash", "intensity_transform", "julia", "line_descriptor", "matlab",
            "ovis", "phase_unwrapping", "rapid", "reg", "saliency", "shape", "signal",
            "structured_light", "surface_matching", "viz", "xstereo",
        ]:
            rmdir(self, os.path.join(self._extra_modules_folder, module))

        ## Fix Freetype discovery logic in freetype extra module
        if self.options.freetype:
            freetype_cmake = os.path.join(self._extra_modules_folder, "freetype", "CMakeLists.txt")
            replace_in_file(self, freetype_cmake, "ocv_check_modules(FREETYPE freetype2)", "find_package(Freetype REQUIRED MODULE)")
            replace_in_file(self, freetype_cmake, "FREETYPE_", "Freetype_")

            replace_in_file(self, freetype_cmake, "ocv_check_modules(HARFBUZZ harfbuzz)", "find_package(harfbuzz REQUIRED CONFIG)")
            replace_in_file(self, freetype_cmake, "HARFBUZZ_", "harfbuzz_")

    def generate(self):
        tc = CMakeToolchain(self)
        tc.variables["OPENCV_CONFIG_INSTALL_PATH"] = "cmake"
        tc.variables["OPENCV_BIN_INSTALL_PATH"] = "bin"
        tc.variables["OPENCV_LIB_INSTALL_PATH"] = "lib"
        tc.variables["OPENCV_3P_LIB_INSTALL_PATH"] = "lib"
        tc.variables["OPENCV_OTHER_INSTALL_PATH"] = "res"
        tc.variables["OPENCV_LICENSES_INSTALL_PATH"] = "licenses"

        tc.variables["OPENCV_SKIP_CMAKE_CXX_STANDARD"] = valid_min_cppstd(self, 17)

        tc.variables["BUILD_CUDA_STUBS"] = False
        tc.variables["BUILD_DOCS"] = False
        tc.variables["BUILD_EXAMPLES"] = False
        tc.variables["BUILD_FAT_JAVA_LIB"] = False
        tc.variables["BUILD_IPP_IW"] = self.options.with_ipp == "opencv-icv"
        tc.variables["BUILD_ITT"] = False
        tc.variables["BUILD_JASPER"] = False
        tc.variables["BUILD_JAVA"] = False
        tc.variables["BUILD_JPEG"] = False
        tc.variables["BUILD_OPENJPEG"] = False
        tc.variables["BUILD_TESTS"] = False
        tc.variables["BUILD_PROTOBUF"] = False
        tc.variables["BUILD_PACKAGE"] = False
        tc.variables["BUILD_PERF_TESTS"] = False
        tc.variables["BUILD_USE_SYMLINKS"] = False
        tc.variables["BUILD_opencv_apps"] = False
        tc.variables["BUILD_opencv_java"] = False
        tc.variables["BUILD_opencv_java_bindings_gen"] = False
        tc.variables["BUILD_opencv_js"] = False
        tc.variables["BUILD_ZLIB"] = False
        tc.variables["BUILD_PNG"] = False
        tc.variables["BUILD_TIFF"] = False
        tc.variables["BUILD_WEBP"] = False
        tc.variables["BUILD_TBB"] = False
        tc.variables["BUILD_CLAPACK"] = False
        tc.variables["OPENCV_FORCE_3RDPARTY_BUILD"] = False
        tc.variables["OPENCV_PYTHON_SKIP_DETECTION"] = True
        tc.variables["BUILD_opencv_python2"] = False
        tc.variables["BUILD_opencv_python3"] = False
        tc.variables["BUILD_opencv_python_bindings_g"] = False
        tc.variables["BUILD_opencv_python_tests"] = False
        tc.variables["BUILD_opencv_ts"] = False

        tc.variables["WITH_1394"] = False
        tc.variables["WITH_ARAVIS"] = False
        tc.variables["WITH_CLP"] = False
        tc.variables["WITH_NVCUVID"] = False

        tc.variables["WITH_FFMPEG"] = self.options.get_safe("with_ffmpeg", False)
        if self.options.get_safe("with_ffmpeg"):
            tc.variables["OPENCV_FFMPEG_SKIP_BUILD_CHECK"] = True
            tc.variables["OPENCV_FFMPEG_SKIP_DOWNLOAD"] = True
            # opencv will not search for ffmpeg package, but for
            # libavcodec;libavformat;libavutil;libswscale modules
            tc.variables["OPENCV_FFMPEG_USE_FIND_PACKAGE"] = "ffmpeg"
            tc.variables["OPENCV_INSTALL_FFMPEG_DOWNLOAD_SCRIPT"] = False
            tc.variables["OPENCV_FFMPEG_ENABLE_LIBAVDEVICE"] = False
            ffmpeg_libraries = []
            for component in ["avcodec",  "avformat", "avutil", "swscale", "avresample"]:
                if component == "avutil" or self.dependencies["ffmpeg"].options.get_safe(component):
                    ffmpeg_libraries.append(f"ffmpeg::{component}")
                    ffmpeg_component_version = self.dependencies["ffmpeg"].cpp_info.components[component].get_property("component_version")
                    tc.variables[f"FFMPEG_lib{component}_VERSION"] = ffmpeg_component_version
            tc.variables["FFMPEG_LIBRARIES"] = ";".join(ffmpeg_libraries)

        tc.variables["WITH_GSTREAMER"] = False
        tc.variables["WITH_HPX"] = False
        tc.variables["WITH_IMGCODEC_GIF"] = self.options.get_safe("with_imgcodec_gif", False)
        tc.variables["WITH_IMGCODEC_HDR"] = self.options.get_safe("with_imgcodec_hdr", False)
        tc.variables["WITH_IMGCODEC_PFM"] = self.options.get_safe("with_imgcodec_pfm", False)
        tc.variables["WITH_IMGCODEC_PXM"] = self.options.get_safe("with_imgcodec_pxm", False)
        tc.variables["WITH_IMGCODEC_SUNRASTER"] = self.options.get_safe("with_imgcodec_sunraster", False)
        tc.variables["WITH_IPP"] = bool(self.options.with_ipp)
        if self.options.with_ipp == "intel-ipp":
            ipp_root = self.dependencies["intel-ipp"].package_folder.replace("\\", "/")
            tc.variables["IPPROOT"] = ipp_root
            tc.variables["IPPIWROOT"] = ipp_root
        tc.variables["WITH_ITT"] = False
        tc.variables["WITH_LIBREALSENSE"] = False
        tc.variables["WITH_MFX"] = False
        tc.variables["WITH_OPENCL"] = self.options.get_safe("with_opencl", False)
        tc.variables["WITH_OPENCLAMDBLAS"] = False
        tc.variables["WITH_OPENCLAMDFFT"] = False
        tc.variables["WITH_OPENCL_SVM"] = False
        tc.variables["WITH_OPENGL"] = False
        tc.variables["WITH_TBB"] = self.options.parallel == "tbb"
        tc.variables["WITH_OPENMP"] = self.options.parallel == "openmp"
        tc.variables["WITH_OPENNI"] = False
        tc.variables["WITH_OPENNI2"] = False
        tc.variables["WITH_CAROTENE"] = False
        tc.variables["WITH_PVAPI"] = False
        tc.variables["WITH_QT"] = self.options.get_safe("with_qt", False)
        tc.variables["WITH_V4L"] = self.options.get_safe("with_v4l", False)
        tc.variables["WITH_VA"] = False
        tc.variables["WITH_VA_INTEL"] = False
        tc.variables["WITH_VTK"] = False
        # Vulkan is only used by a couple of experimental/internal DNN backend code paths upstream;
        # not worth the extra vulkan-headers requirement for a recipe option.
        tc.variables["WITH_VULKAN"] = False
        tc.variables["WITH_XIMEA"] = False
        tc.variables["WITH_XINE"] = False
        tc.variables["WITH_LAPACK"] = False
        # No CCI consumer or issue has ever asked for GDAL (geospatial raster) or GDCM (DICOM
        # medical imaging) support; both are large, rarely-touched optional integrations.
        tc.variables["WITH_GDAL"] = False
        tc.variables["WITH_GDCM"] = False
        # Tesseract OCR backend for the text module: unmaintained upstream integration with no
        # known CCI consumer; the text module builds fine without it (scene text detection still
        # works, only the OCRTesseract recognition backend is unavailable).
        tc.variables["WITH_TESSERACT"] = False
        # ONNX Runtime is an optional additional DNN inference backend (on top of OpenCV's own,
        # always-available ONNX importer); no evidence anyone needs it yet.
        tc.variables["WITH_ONNXRUNTIME"] = False
        # Disable the network fetch of a bundled Unicode font at configure time: Conan builds
        # must not reach out to arbitrary URLs outside of the declared conandata.yml sources.
        tc.variables["WITH_UNIFONT"] = False

        tc.variables["WITH_GTK"] = self.options.get_safe("with_gtk", False)
        tc.variables["WITH_GTK_2_X"] = False
        tc.variables["WITH_WEBP"] = self.options.get_safe("with_webp", False)
        tc.variables["WITH_JPEG"] = bool(self.options.get_safe("with_jpeg", False))
        tc.variables["WITH_PNG"] = self.options.get_safe("with_png", False)
        if self._has_with_tiff_option:
            tc.variables["WITH_TIFF"] = self.options.get_safe("with_tiff", False)
        if self._has_with_jpeg2000_option:
            tc.variables["WITH_JASPER"] = self.options.get_safe("with_jpeg2000") == "jasper"
            tc.variables["WITH_OPENJPEG"] = self.options.get_safe("with_jpeg2000") == "openjpeg"
        tc.variables["WITH_OPENEXR"] = self.options.get_safe("with_openexr", False)
        tc.variables["WITH_EIGEN"] = self.options.with_eigen
        tc.variables["WITH_DSHOW"] = self._is_cl_like
        tc.variables["WITH_MSMF"] = self.options.get_safe("with_msmf", False)
        tc.variables["WITH_MSMF_DXVA"] = self.options.get_safe("with_msmf_dxva", False)
        tc.variables["OPENCV_MODULES_PUBLIC"] = "opencv"
        tc.variables["OPENCV_ENABLE_NONFREE"] = self.options.nonfree

        if self.options.cpu_baseline or self.options.cpu_baseline == "":
            tc.variables["CPU_BASELINE"] = self.options.cpu_baseline

        if self.options.cpu_dispatch or self.options.cpu_dispatch == "":
            tc.variables["CPU_DISPATCH"] = self.options.cpu_dispatch

        tc.variables["OPENCV_DNN_CUDA"] = self.options.get_safe("dnn_cuda", False)

        tc.variables["WITH_OPENVINO"] = self.options.get_safe("with_openvino", False)
        tc.variables["WITH_TIMVX"] = False

        tc.variables["ENABLE_DELAYLOAD"] = False
        tc.variables["WITH_CANN"] = False
        tc.variables["WITH_SPNG"] = False # TODO: change with_png recipe option in order to use either libpng or libspng
        tc.variables["WITH_WAYLAND"] = self.options.get_safe("with_wayland", False)

        tc.variables["WITH_AVIF"] = self.options.get_safe("with_avif", False)
        tc.variables["WITH_FLATBUFFERS"] = self.options.get_safe("with_flatbuffers", False)

        tc.variables["WITH_KLEIDICV"] = False
        tc.variables["WITH_NDSRVP"] = False
        tc.variables["WITH_FASTCV"] = False
        tc.variables["OBSENSOR_USE_ORBBEC_SDK"] = False
        if is_apple_os(self):
            tc.variables["WITH_OBSENSOR"] = False
        tc.variables["WITH_ZLIB_NG"] = False

        tc.variables["WITH_HAL_RVV"] = False

        # Special world option merging all enabled modules into one big library file
        tc.variables["BUILD_opencv_world"] = self.options.world

        # Main modules
        tc.variables["BUILD_opencv_core"] = True
        for module in OPENCV_MAIN_MODULES_OPTIONS:
            tc.variables[f"BUILD_opencv_{module}"] = self.options.get_safe(module, False)
        tc.variables["WITH_PROTOBUF"] = self.options.get_safe("with_protobuf", False)
        if self.options.get_safe("with_protobuf"):
            tc.variables["PROTOBUF_UPDATE_FILES"] = True
        tc.variables["WITH_ADE"] = self.options.gapi

        # Extra modules
        tc.variables["OPENCV_EXTRA_MODULES_PATH"] = self._extra_modules_folder.replace("\\", "/")
        tc.variables["BUILD_opencv_cudev"] = self.options.with_cuda
        for module in OPENCV_EXTRA_MODULES_OPTIONS:
            tc.variables[f"BUILD_opencv_{module}"] = self.options.get_safe(module, False)
        for module in [
            "alphamat", "cannops", "cnn_3dobj", "cvv", "dnns_easily_fooled", "dpm", "fastcv", "fuzzy",
            "hdf", "hfs", "img_hash", "intensity_transform", "julia", "line_descriptor", "matlab",
            "ovis", "phase_unwrapping", "rapid", "reg", "saliency", "shape", "signal",
            "structured_light", "surface_matching", "viz", "xstereo",
        ]:
            tc.variables[f"BUILD_opencv_{module}"] = False

        if self.options.get_safe("with_jpeg2000") == "openjpeg":
            openjpeg_version = Version(self.dependencies["openjpeg"].ref.version)
            tc.variables["OPENJPEG_MAJOR_VERSION"] = openjpeg_version.major
            tc.variables["OPENJPEG_MINOR_VERSION"] = openjpeg_version.minor
            tc.variables["OPENJPEG_BUILD_VERSION"] = openjpeg_version.patch

        tc.variables["WITH_CUDA"] = self.options.with_cuda
        if self.options.with_cuda:
            # This allows compilation on older GCC/NVCC, otherwise build errors.
            tc.variables["CUDA_NVCC_FLAGS"] = "--expt-relaxed-constexpr"
            if self.options.cuda_arch_bin:
                tc.variables["CUDA_ARCH_BIN"] = self.options.cuda_arch_bin
        tc.variables["WITH_CUBLAS"] = self.options.get_safe("with_cublas", False)
        tc.variables["WITH_CUFFT"] = self.options.get_safe("with_cufft", False)
        tc.variables["WITH_CUDNN"] = self.options.get_safe("with_cudnn", False)

        tc.variables["ENABLE_PIC"] = self.options.get_safe("fPIC", True)
        tc.variables["ENABLE_CCACHE"] = False

        if self._is_cl_like:
            tc.variables["BUILD_WITH_STATIC_CRT"] = self._is_cl_like_static_runtime

        if self.settings.os == "Android":
            tc.variables["BUILD_ANDROID_EXAMPLES"] = False
        tc.cache_variables["CV_TRACE"] = False

        tc.generate()

        cmake_deps = CMakeDeps(self)
        if self.options.get_safe("with_protobuf"):
            # OpenCVFindProtobuf.cmake calls find_package(Protobuf CONFIG) with a capital P, but
            # protobuf's own recipe sets cmake_file_name="protobuf" (lowercase). Under the classic
            # CMakeDeps generator this is harmless (CMake's own dual Config.cmake/-config.cmake
            # lookup covers the case mismatch once *some* path hint exists), but the newer
            # CMakeConfigDeps generator (enabled via -c tools.cmake.cmakedeps:new=will_break_next)
            # only writes a path hint for the exact declared name ("protobuf_DIR", never
            # "Protobuf_DIR"), so find_package(Protobuf CONFIG) can't locate it at all and
            # OpenCV's own code falls back to a dumb module-mode search that doesn't know about
            # protobuf's abseil dependency, breaking dnn's generated protobuf sources. Declaring
            # the capitalized spelling as a variant makes CMakeConfigDeps also emit "Protobuf_DIR"
            # (a no-op under classic CMakeDeps, which doesn't read this property at all).
            for build_context in (False, True):
                cmake_deps.set_property("protobuf", "cmake_file_name_variants", ["Protobuf"],
                                        build_context=build_context)
        cmake_deps.generate()

        if self.options.get_safe("with_wayland") or self.options.get_safe("with_gtk"):
            deps = PkgConfigDeps(self)
            if self.options.get_safe("with_wayland"):
                deps.build_context_activated = ["wayland-protocols"]
            deps.generate()

    def build(self):
        self._patch_sources()
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE", src=self.source_folder, dst=os.path.join(self.package_folder, "licenses"))
        cmake = CMake(self)
        cmake.install()
        rmdir(self, os.path.join(self.package_folder, "cmake"))
        if os.path.isfile(os.path.join(self.package_folder, "setup_vars_opencv5.cmd")):
            rename(self, os.path.join(self.package_folder, "setup_vars_opencv5.cmd"),
                         os.path.join(self.package_folder, "res", "setup_vars_opencv5.cmd"))

        self._create_cmake_module_variables(os.path.join(self.package_folder, self._module_vars_rel_path))

    def _create_cmake_module_variables(self, module_file):
        """
        Define several CMake variables from upstream CMake config file not defined by default by CMakeDeps.
        See https://github.com/opencv/opencv/blob/5.0.0/cmake/templates/OpenCVConfig.cmake.in
        """
        v = Version(self.version)
        content = textwrap.dedent(f"""\
            if(NOT DEFINED OpenCV_LIBS)
                set(OpenCV_LIBS opencv::opencv)
            endif()
            if(NOT DEFINED OpenCV_VERSION_MAJOR)
                set(OpenCV_VERSION_MAJOR {v.major})
            endif()
            if(NOT DEFINED OpenCV_VERSION_MINOR)
                set(OpenCV_VERSION_MINOR {v.minor})
            endif()
            if(NOT DEFINED OpenCV_VERSION_PATCH)
                set(OpenCV_VERSION_PATCH {v.patch})
            endif()
        """)
        save(self, module_file, content)

    @property
    def _module_vars_rel_path(self):
        return os.path.join("lib", "cmake", f"conan-official-{self.name}-variables.cmake")

    @property
    def _module_target_rel_path(self):
        return os.path.join("lib", "cmake", f"conan-official-{self.name}-targets.cmake")

    @staticmethod
    def _cmake_target(module):
        if module in ("ippiw", "opencv.sfm.correspondence", "opencv.sfm.multiview", "opencv.sfm.numeric"):
            return module
        return f"opencv_{module}"

    def package_info(self):
        version = self.version.split(".")
        version = "".join(version) if self.settings.os == "Windows" else ""
        debug = "d" if self.settings.build_type == "Debug" and self.settings.os == "Windows" else ""

        def get_libs(module):
            if module == "ippiw":
                return [
                    f"{module}{debug}",
                    "ippicvmt" if self.settings.os == "Windows" else "ippicv",
                ]
            elif module in ("opencv.sfm.correspondence", "opencv.sfm.multiview", "opencv.sfm.numeric"):
                return [module]
            else:
                libs = [f"opencv_{module}{version}{debug}"]
                if module in ["core", "world"] and not self.options.shared:
                    lib_exclude_filter = r"(opencv_|ippi|opencv\.sfm\.).*"
                    libs += list(filter(lambda x: not re.match(lib_exclude_filter, x), collect_libs(self)))
                return libs

        def add_components(modules):
            if self.options.world:
                self.cpp_info.components["opencv_world"].set_property("cmake_target_name", "opencv_world")
                self.cpp_info.components["opencv_world"].libs = get_libs("world")
                self.cpp_info.components["opencv_world"].resdirs = ["res"]
                if self.settings.os != "Windows":
                    self.cpp_info.components["opencv_world"].includedirs.append(os.path.join("include", "opencv5"))
                world_requires = set()
                world_requires_exclude = set()
                world_system_libs = set()
                world_frameworks = set()

            for module, values in modules.items():
                if not values.get("is_built"):
                    continue
                cmake_target = self._cmake_target(module)
                conan_component = cmake_target
                # TODO: we should also define COMPONENTS names of each target for find_package() but
                # not possible yet in CMakeDeps. See https://github.com/conan-io/conan/issues/10258
                self.cpp_info.components[conan_component].set_property("cmake_target_name", cmake_target)
                self.cpp_info.components[conan_component].resdirs = ["res"]
                if self.settings.os != "Windows":
                    self.cpp_info.components[conan_component].includedirs.append(os.path.join("include", "opencv5"))

                module_requires = values.get("requires", [])
                module_system_libs = []
                for _condition, _system_libs in values.get("system_libs", []):
                    if _condition:
                        module_system_libs.extend(_system_libs)
                module_frameworks = []
                for _condition, _frameworks in values.get("frameworks", []):
                    if _condition:
                        module_frameworks.extend(_frameworks)

                if self.options.world and values.get("is_part_of_world", True):
                    self.cpp_info.components[conan_component].requires = ["opencv_world"]
                    world_requires.update(module_requires)
                    world_requires_exclude.add(conan_component)
                    world_system_libs.update(module_system_libs)
                    world_frameworks.update(module_frameworks)
                else:
                    self.cpp_info.components[conan_component].libs = get_libs(module)
                    self.cpp_info.components[conan_component].requires = module_requires
                    self.cpp_info.components[conan_component].system_libs = module_system_libs
                    self.cpp_info.components[conan_component].frameworks = module_frameworks

                if module != cmake_target:
                    conan_component_alias = conan_component + "_alias"
                    self.cpp_info.components[conan_component_alias].requires = [conan_component]
                    self.cpp_info.components[conan_component_alias].bindirs = []
                    self.cpp_info.components[conan_component_alias].includedirs = []
                    self.cpp_info.components[conan_component_alias].libdirs = []

            if self.options.world:
                self.cpp_info.components["opencv_world"].requires = list(world_requires - world_requires_exclude)
                self.cpp_info.components["opencv_world"].system_libs = list(world_system_libs)
                self.cpp_info.components["opencv_world"].frameworks = list(world_frameworks)

        self.cpp_info.set_property("cmake_file_name", "OpenCV")
        self.cpp_info.set_property("cmake_build_modules", [self._module_vars_rel_path])

        # A global (package-level, not per-component) declaration of the short module names
        # (e.g. "core", "imgproc") that find_package(OpenCV COMPONENTS ...) should accept --
        # matching the names real OpenCV users conventionally write, and matching upstream
        # OpenCV's own generated config. This is deliberately independent of cmake_target_name
        # (e.g. "opencv_core"): CMakeConfigDeps validates find_package() COMPONENTS against
        # whatever this property lists, not against the component/target names, so the two can
        # differ. Classic CMakeDeps doesn't read this property (harmless no-op there).
        internal_only_components = {
            "ippiw", "opencv.sfm.correspondence", "opencv.sfm.multiview", "opencv.sfm.numeric",
        }
        self.cpp_info.set_property("cmake_components", [
            module for module, values in self._opencv_modules.items()
            if values.get("is_built") and module not in internal_only_components
        ])

        add_components(self._opencv_modules)
