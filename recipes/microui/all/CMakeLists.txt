cmake_minimum_required(VERSION 3.15)
project(microui LANGUAGES C)

add_library(microui
    src/src/microui.c
    src/src/microui.h
)

include(GNUInstallDirs)
install(TARGETS microui
    EXPORT microui-targets
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
)
install(DIRECTORY src/src/
    DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/
    FILES_MATCHING PATTERN "*.h"
)
