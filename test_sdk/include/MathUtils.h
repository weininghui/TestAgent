#ifndef MATH_UTILS_H
#define MATH_UTILS_H

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Add two integers
 * @param a First operand
 * @param b Second operand
 * @return Sum of a and b
 */
int add(int a, int b);

/**
 * @brief Subtract b from a
 * @param a First operand
 * @param b Second operand
 * @return Result of a - b
 */
int subtract(int a, int b);

/**
 * @brief Multiply two integers
 * @param a First operand
 * @param b Second operand
 * @return Product of a and b
 */
int multiply(int a, int b);

/**
 * @brief Divide a by b
 * @param a Dividend
 * @param b Divisor (must not be zero)
 * @return Quotient of a / b
 */
double divide(double a, double b);

#ifdef __cplusplus
}
#endif

#endif /* MATH_UTILS_H */
