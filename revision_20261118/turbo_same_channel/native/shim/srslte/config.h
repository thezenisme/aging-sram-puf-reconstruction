#ifndef TURBO_LOCAL_SRSLTE_CONFIG_H
#define TURBO_LOCAL_SRSLTE_CONFIG_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#ifndef bzero
#define bzero(pointer, bytes) memset((pointer), 0, (bytes))
#endif
#define SRSLTE_API
#define SRSLTE_SUCCESS 0
#define SRSLTE_ERROR (-1)
#define SRSLTE_ERROR_INVALID_INPUTS (-2)
#endif
