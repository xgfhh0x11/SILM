cmake_minimum_required(VERSION 3.15)
project(InterruptLatencyMonitor)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Executable
add_executable(daemon daemon.cpp)

# Link libraries
target_link_libraries(daemon)

# Compiler options
if(MSVC)
    target_compile_options(daemon PRIVATE /W4 /WX-)
else()
    target_compile_options(daemon PRIVATE -Wall -Wextra)
endif()

