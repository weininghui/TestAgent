#include <gtest/gtest.h>
#include "my_sdk/api.hpp"

using my_sdk::Calculator;
using my_sdk::Status;
using my_sdk::clamp;
using my_sdk::parse_status;
using my_sdk::version;

TEST(MySdkTest, Version) {
    EXPECT_EQ(version(), "1.0.0");
}

TEST(MySdkTest, CalculatorAdd) {
    Calculator calc;
    EXPECT_EQ(calc.add(2, 3), 5);
}

TEST(MySdkTest, CalculatorStaticMul) {
    EXPECT_EQ(Calculator::mul(4, 3), 12);
}

TEST(MySdkTest, ClampTemplate) {
    EXPECT_EQ(clamp(5, 0, 10), 5);
    EXPECT_EQ(clamp(-1, 0, 10), 0);
    EXPECT_EQ(clamp(99, 0, 10), 10);
}

TEST(MySdkTest, EnumClassStatus) {
    EXPECT_EQ(parse_status("ok"), Status::Ok);
    EXPECT_EQ(parse_status("missing"), Status::NotFound);
}
