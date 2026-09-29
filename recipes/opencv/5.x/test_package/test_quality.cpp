#include <opencv2/core.hpp>
#include <opencv2/quality/qualitymse.hpp>

int main() {
    cv::Mat reference = cv::Mat::zeros(50, 50, CV_8UC1);
    auto quality_mse = cv::quality::QualityMSE::create(reference);
    return 0;
}
