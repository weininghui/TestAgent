#ifndef STRING_HELPER_H
#define STRING_HELPER_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Get the length of a string
 * @param str Null-terminated string
 * @return Length of the string (excluding null terminator)
 */
size_t strlen_custom(const char* str);

/**
 * @brief Copy string from src to dst
 * @param dst Destination buffer
 * @param src Source string
 * @param dst_size Size of destination buffer
 * @return Number of bytes copied
 */
size_t strcpy_custom(char* dst, const char* src, size_t dst_size);

/**
 * @brief Concatenate src to dst
 * @param dst Destination buffer containing first string
 * @param src String to append
 * @param dst_size Size of destination buffer
 * @return Total length of concatenated string
 */
size_t strcat_custom(char* dst, const char* src, size_t dst_size);

/**
 * @brief Compare two strings
 * @param str1 First string
 * @param str2 Second string
 * @return 0 if equal, negative if str1 < str2, positive if str1 > str2
 */
int strcmp_custom(const char* str1, const char* str2);

#ifdef __cplusplus
}
#endif

#endif /* STRING_HELPER_H */
