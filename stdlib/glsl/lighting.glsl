/**
 * Lighting utilities for Termin engine (UBO mode).
 *
 * Usage in your shader:
 *   #include "lighting.glsl"
 *
 * Requires:
 *   @features lighting_ubo
 *
 * Provides:
 *   - Light type constants
 *   - Accessor functions for light data
 *   - Attenuation functions
 *   - Spotlight falloff
 */

#ifndef LIGHTING_GLSL
#define LIGHTING_GLSL

// ============== Light Types ==============
const int LIGHT_TYPE_DIRECTIONAL = 0;
const int LIGHT_TYPE_POINT       = 1;
const int LIGHT_TYPE_SPOT        = 2;

const int MAX_LIGHTS = 8;

// ============== Lighting UBO ==============
// Light data structure matching C++ LightDataStd140
struct LightData {
    vec4 color_intensity;      // color.rgb, intensity
    vec4 direction_range;      // direction.xyz, range
    vec4 position_type;        // position.xyz, type
    vec4 attenuation_inner;    // attenuation.xyz, inner_angle
    vec4 outer_cascade;        // outer_angle, cascade_count, cascade_blend, blend_distance
};

// Lighting uniform block (std140 layout)
// Note: binding point is set via glUniformBlockBinding in C++ (for GLSL 330 compatibility)
layout(std140) uniform LightingBlock {
    LightData u_lights[MAX_LIGHTS];      // 80 bytes * 8 = 640 bytes
    vec4 u_ambient_data;                 // ambient_color.rgb, ambient_intensity
    vec4 u_camera_light_count;           // camera_position.xyz, light_count
    vec4 u_shadow_settings;              // shadow_method, shadow_softness, shadow_bias, _pad
};

// ============== Accessor Functions ==============

int get_light_count() {
    return int(u_camera_light_count.w);
}

int get_light_type(int i) {
    return int(u_lights[i].position_type.w);
}

vec3 get_light_color(int i) {
    return u_lights[i].color_intensity.rgb;
}

float get_light_intensity(int i) {
    return u_lights[i].color_intensity.w;
}

vec3 get_light_direction(int i) {
    return u_lights[i].direction_range.xyz;
}

vec3 get_light_position(int i) {
    return u_lights[i].position_type.xyz;
}

float get_light_range(int i) {
    return u_lights[i].direction_range.w;
}

vec3 get_light_attenuation(int i) {
    return u_lights[i].attenuation_inner.xyz;
}

float get_light_inner_angle(int i) {
    return u_lights[i].attenuation_inner.w;
}

float get_light_outer_angle(int i) {
    return u_lights[i].outer_cascade.x;
}

int get_light_cascade_count(int i) {
    return int(u_lights[i].outer_cascade.y);
}

int get_light_cascade_blend(int i) {
    return int(u_lights[i].outer_cascade.z);
}

float get_light_blend_distance(int i) {
    return u_lights[i].outer_cascade.w;
}

vec3 get_ambient_color() {
    return u_ambient_data.rgb;
}

float get_ambient_intensity() {
    return u_ambient_data.w;
}

vec3 get_camera_position() {
    return u_camera_light_count.xyz;
}

int get_shadow_method() {
    return int(u_shadow_settings.x);
}

float get_shadow_softness() {
    return u_shadow_settings.y;
}

float get_shadow_bias() {
    return u_shadow_settings.z;
}

// ============== Common Functions ==============

/**
 * Compute distance attenuation for point/spot lights.
 *
 * Uses the formula: 1 / (constant + linear*d + quadratic*d^2)
 * With range cutoff.
 *
 * Parameters:
 *   attenuation: vec3(constant, linear, quadratic)
 *   range: maximum light range (0 = infinite)
 *   dist: distance from light to fragment
 *
 * Returns:
 *   Attenuation factor [0, 1]
 */
float compute_distance_attenuation(vec3 attenuation, float range, float dist) {
    float denom = attenuation.x + attenuation.y * dist + attenuation.z * dist * dist;
    if (denom <= 0.0) {
        return 1.0;
    }
    float w = 1.0 / denom;
    if (range > 0.0 && dist > range) {
        w = 0.0;
    }
    return w;
}

/**
 * Compute spotlight cone falloff.
 *
 * Parameters:
 *   light_dir: normalized direction the spotlight is pointing
 *   L: normalized direction from fragment to light
 *   inner_angle: inner cone angle in radians (full intensity)
 *   outer_angle: outer cone angle in radians (zero intensity)
 *
 * Returns:
 *   Spotlight weight [0, 1] with smooth falloff
 */
float compute_spot_weight(vec3 light_dir, vec3 L, float inner_angle, float outer_angle) {
    float cos_theta = dot(light_dir, -L);
    float cos_outer = cos(outer_angle);
    float cos_inner = cos(inner_angle);

    if (cos_theta <= cos_outer) return 0.0;
    if (cos_theta >= cos_inner) return 1.0;

    float t = (cos_theta - cos_outer) / (cos_inner - cos_outer);
    return t * t * (3.0 - 2.0 * t); // smoothstep
}

/**
 * Blinn-Phong specular highlight.
 *
 * Parameters:
 *   N: surface normal (normalized)
 *   L: direction to light (normalized)
 *   V: direction to viewer (normalized)
 *   shininess: specular exponent (higher = smaller highlight)
 *
 * Returns:
 *   Specular intensity
 */
float blinn_phong_specular(vec3 N, vec3 L, vec3 V, float shininess) {
    vec3 H = normalize(L + V);
    float NdotH = max(dot(N, H), 0.0);
    return pow(NdotH, shininess);
}

#endif // LIGHTING_GLSL
