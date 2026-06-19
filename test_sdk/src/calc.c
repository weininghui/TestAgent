#include "calc.h"

int calc_add(int a, int b) {
    return a + b;
}

int calc_sub(int a, int b) {
    return a - b;
}

int calc_mul(int a, int b) {
    return a * b;
}

double calc_div(int a, int b) {
    if (b == 0) {
        return 0.0;
    }
    return (double)a / (double)b;
}
