#include <opencv2/core.hpp>
#include <opencv2/objdetect/aruco_dictionary.hpp>

int main() {
    auto dictionary = cv::aruco::getPredefinedDictionary(cv::aruco::DICT_4X4_50);
    return 0;
}
