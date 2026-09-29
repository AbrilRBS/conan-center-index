#include <opencv2/datasets/fr_lfw.hpp>

int main() {
    auto dataset = cv::datasets::FR_lfw::create();
    return 0;
}
