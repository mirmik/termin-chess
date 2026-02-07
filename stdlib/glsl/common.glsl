/**
 * Common GLSL utilities for Termin engine.
 *
 * Usage in your shader:
 *   #include "common"
 *
 * Provides:
 *   - Constants (PI, etc.)
 *   - Common math functions
 *   - Color space conversions
 */

#ifndef COMMON_GLSL
#define COMMON_GLSL

// ============== Constants ==============
const float PI = 3.14159265359;
const float TWO_PI = 6.28318530718;
const float HALF_PI = 1.57079632679;
const float INV_PI = 0.31830988618;

const float EPSILON = 0.0001;

// ============== Math utilities ==============

/**
 * Remap value from one range to another.
 */
float remap(float value, float from_min, float from_max, float to_min, float to_max) {
    float t = (value - from_min) / (from_max - from_min);
    return mix(to_min, to_max, t);
}

/**
 * Saturate (clamp to 0-1).
 */
float saturate(float x) {
    return clamp(x, 0.0, 1.0);
}

vec3 saturate(vec3 x) {
    return clamp(x, 0.0, 1.0);
}

/**
 * Square of a value.
 */
float sq(float x) {
    return x * x;
}

// ============== Color utilities ==============

/**
 * sRGB to linear color space.
 */
vec3 srgb_to_linear(vec3 color) {
    return pow(color, vec3(2.2));
}

/**
 * Linear to sRGB color space.
 */
vec3 linear_to_srgb(vec3 color) {
    return pow(color, vec3(1.0 / 2.2));
}

/**
 * Luminance (perceived brightness).
 */
float luminance(vec3 color) {
    return dot(color, vec3(0.2126, 0.7152, 0.0722));
}

// ============== Normal mapping utilities ==============

/**
 * Unpack normal from normal map (0-1 to -1..1).
 */
vec3 unpack_normal(vec3 packed) {
    return packed * 2.0 - 1.0;
}

/**
 * Construct TBN matrix from normal and tangent.
 */
mat3 construct_tbn(vec3 normal, vec4 tangent) {
    vec3 N = normalize(normal);
    vec3 T = normalize(tangent.xyz);
    vec3 B = cross(N, T) * tangent.w;
    return mat3(T, B, N);
}

#endif // COMMON_GLSL
