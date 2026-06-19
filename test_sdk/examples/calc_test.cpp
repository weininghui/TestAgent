#include <gtest/gtest.h>

extern "C" {
#include "calc.h"
}

TEST(CalcTest, Add) {
    EXPECT_EQ(calc_add(2, 3), 5);
}

TEST(CalcTest, Sub) {
    EXPECT_EQ(calc_sub(5, 2), 3);
}

TEST(CalcTest, Mul) {
    EXPECT_EQ(calc_mul(4, 3), 12);
}

TEST(CalcTest, Div) {
    EXPECT_DOUBLE_EQ(calc_div(10, 2), 5.0);
}
