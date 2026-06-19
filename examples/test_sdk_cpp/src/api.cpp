#include "my_sdk/api.hpp"

namespace my_sdk {

int Calculator::add(int a, int b) const {
    return a + b;
}

int Calculator::sub(int a, int b) const {
    return a - b;
}

int Calculator::mul(int a, int b) {
    return a * b;
}

double Calculator::div(int a, int b) const {
    if (b == 0) return 0.0;
    return static_cast<double>(a) / static_cast<double>(b);
}

std::string version() {
    return "1.0.0";
}

Status parse_status(const std::string& name) {
    if (name == "ok") return Status::Ok;
    if (name == "error") return Status::Error;
    return Status::NotFound;
}

}  // namespace my_sdk
