#include <opencv2/face.hpp>
#include <opencv2/face/facerec.hpp>

int main() {
    auto recognizer = cv::face::LBPHFaceRecognizer::create();
    return 0;
}
