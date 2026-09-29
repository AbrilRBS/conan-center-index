#include <opencv2/bioinspired.hpp>

int main() {
    auto retina = cv::bioinspired::Retina::create(cv::Size(100, 100));
    return 0;
}
