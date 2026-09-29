cmake_minimum_required(VERSION 3.15)
project(test_package LANGUAGES CXX)

enable_testing()

set(TESTED_MODULES
    # Main modules
    "calib" "core" "dnn" "features" "flann" "geometry" "highgui" "imgcodecs"
    "imgproc" "objdetect" "photo" "ptcloud" "stereo" "stitching" "video" "videoio"
    # Extra modules
    "bgsegm" "bioinspired" "ccalib" "datasets" "dnn_superres" "face" "freetype"
    "gapi" "ml" "optflow" "plot" "quality" "rgbd" "sfm" "superres" "text"
    "tracking" "wechat_qrcode" "xfeatures2d" "ximgproc" "xobjdetect" "xphoto"
)

find_package(OpenCV REQUIRED core CONFIG)

foreach(_module ${TESTED_MODULES})
    string(TOUPPER ${_module} _module_upper)
    if(OPENCV_WITH_${_module_upper})
        set(_test_target test_${_module})
        set(_module_target opencv_${_module})
        add_executable(${_test_target} ${_test_target}.cpp)
        target_link_libraries(${_test_target} PRIVATE ${_module_target})
        target_compile_features(${_test_target} PRIVATE cxx_std_17)
        if(NOT ${_module} STREQUAL "highgui")
            add_test(NAME ${_test_target} COMMAND ${_test_target})
        endif()
    endif()
endforeach()
