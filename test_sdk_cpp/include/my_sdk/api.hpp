#pragma once

#include <string>
#include <vector>

namespace my_sdk {

enum class Status {
    Ok,
    Error,
    NotFound,
};

class Calculator {
public:
    Calculator() = default;
    virtual ~Calculator() = default;

    int add(int a, int b) const;
    int sub(int a, int b) const;
    static int mul(int a, int b);
    virtual double div(int a, int b) const;

private:
    int last_result_ = 0;
};

template <typename T>
T clamp(T value, T lo, T hi) {
    if (value < lo) return lo;
    if (value > hi) return hi;
    return value;
}

std::string version();
Status parse_status(const std::string& name);

}  // namespace my_sdk
