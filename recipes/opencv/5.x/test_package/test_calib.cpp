#include <opencv2/calib.hpp>
#include <opencv2/core.hpp>

#include <vector>

int main() {
    std::vector<std::vector<cv::Point3f>> object_points(1);
    std::vector<std::vector<cv::Point2f>> image_points(1);
    for (int i = 0; i < 4; ++i) {
        object_points[0].emplace_back(static_cast<float>(i % 2), static_cast<float>(i / 2), 0.f);
        image_points[0].emplace_back(static_cast<float>(50 + 40 * (i % 2)), static_cast<float>(50 + 40 * (i / 2)));
    }
    try {
        cv::Mat camera_matrix = cv::initCameraMatrix2D(object_points, image_points, cv::Size(200, 200));
    } catch (const cv::Exception&) {
        // The synthetic correspondences above are only meant to exercise linkage against
        // libopencv_calib; degenerate input throwing here is not a link/build failure.
    }
    return 0;
}
