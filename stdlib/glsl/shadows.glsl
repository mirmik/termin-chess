/**
 * Shadow mapping utilities for Termin engine.
 *
 * Usage in your shader:
 *   #include "shadows.glsl"
 *
 * This file declares all required uniforms automatically.
 * The engine sets these uniforms via upload_shadow_maps_to_shader().
 *
 * Functions:
 *   float compute_shadow(int light_index) - hard shadow with hardware PCF
 *   float compute_shadow_pcf(int light_index) - 5x5 PCF soft shadow
 *   float compute_shadow_poisson(int light_index) - Poisson disk (best quality)
 *   float compute_shadow_cascaded(int light_index) - CSM with cascade blending
 *   float compute_shadow_auto(int light_index) - auto-select based on settings
 *
 * Required varying (must be defined in your shader):
 *   in vec3 v_world_pos;
 */

#ifndef SHADOWS_GLSL
#define SHADOWS_GLSL

#ifndef MAX_SHADOW_MAPS
#define MAX_SHADOW_MAPS 16
#endif

#ifndef MAX_LIGHTS
#define MAX_LIGHTS 8
#endif

#ifndef SHADOW_BIAS
#define SHADOW_BIAS 0.005
#endif

// Shadow map uniforms (set by engine)
uniform int u_shadow_map_count;
uniform sampler2DShadow u_shadow_map[MAX_SHADOW_MAPS];
uniform mat4 u_light_space_matrix[MAX_SHADOW_MAPS];
uniform int u_shadow_light_index[MAX_SHADOW_MAPS];

// Cascade uniforms (set by engine)
uniform int u_shadow_cascade_index[MAX_SHADOW_MAPS];
uniform float u_shadow_split_near[MAX_SHADOW_MAPS];
uniform float u_shadow_split_far[MAX_SHADOW_MAPS];

// Per-light cascade settings (only if lighting.glsl not included)
#ifndef LIGHTING_GLSL
uniform int u_light_cascade_count[MAX_LIGHTS];
uniform int u_light_cascade_blend[MAX_LIGHTS];
uniform float u_light_blend_distance[MAX_LIGHTS];
#endif

// View matrix for computing view-space depth
uniform mat4 u_view;

// Shadow settings accessors
// If lighting.glsl is included, use its accessors; otherwise define our own uniforms

#ifdef LIGHTING_GLSL
// lighting.glsl is included - use its accessors
int _get_shadow_method_val() { return get_shadow_method(); }
float _get_shadow_softness_val() { return get_shadow_softness(); }
float _get_shadow_bias_val() { return get_shadow_bias(); }
int _get_cascade_count(int i) { return get_light_cascade_count(i); }
int _get_cascade_blend(int i) { return get_light_cascade_blend(i); }
float _get_blend_distance(int i) { return get_light_blend_distance(i); }
#else
// lighting.glsl not included - define our own uniforms
uniform int u_shadow_method;
uniform float u_shadow_softness;
uniform float u_shadow_bias;

int _get_shadow_method_val() { return u_shadow_method; }
float _get_shadow_softness_val() { return u_shadow_softness; }
float _get_shadow_bias_val() { return u_shadow_bias; }
int _get_cascade_count(int i) { return u_light_cascade_count[i]; }
int _get_cascade_blend(int i) { return u_light_cascade_blend[i]; }
float _get_blend_distance(int i) { return u_light_blend_distance[i]; }
#endif

// 16-sample Poisson disk for high-quality shadow sampling
const int POISSON_SAMPLES = 16;
const vec2 poissonDisk[16] = vec2[](
    vec2(-0.94201624, -0.39906216),
    vec2( 0.94558609, -0.76890725),
    vec2(-0.09418410, -0.92938870),
    vec2( 0.34495938,  0.29387760),
    vec2(-0.91588581,  0.45771432),
    vec2(-0.81544232, -0.87912464),
    vec2(-0.38277543,  0.27676845),
    vec2( 0.97484398,  0.75648379),
    vec2( 0.44323325, -0.97511554),
    vec2( 0.53742981, -0.47373420),
    vec2(-0.26496911, -0.41893023),
    vec2( 0.79197514,  0.19090188),
    vec2(-0.24188840,  0.99706507),
    vec2(-0.81409955,  0.91437590),
    vec2( 0.19984126,  0.78641367),
    vec2( 0.14383161, -0.14100790)
);

/**
 * Get effective shadow bias (uniform or fallback to define).
 */
float _get_shadow_bias() {
    float bias = _get_shadow_bias_val();
    return bias > 0.0 ? bias : SHADOW_BIAS;
}

/**
 * Sample single shadow map at given index using selected method.
 */
float _sample_shadow_map(int sm, vec3 world_pos, float bias) {
    vec4 light_space_pos = u_light_space_matrix[sm] * vec4(world_pos, 1.0);
    vec3 proj_coords = light_space_pos.xyz / light_space_pos.w;
    proj_coords = proj_coords * 0.5 + 0.5;

    // Bounds check
    if (proj_coords.x < 0.0 || proj_coords.x > 1.0 ||
        proj_coords.y < 0.0 || proj_coords.y > 1.0 ||
        proj_coords.z < 0.0 || proj_coords.z > 1.0) {
        return 1.0;
    }

    float compare_depth = proj_coords.z - bias;
    int method = _get_shadow_method_val();
    float softness = max(_get_shadow_softness_val(), 0.0);

    // Use shadow method
    if (method == 0) {
        // Hard shadow
        return texture(u_shadow_map[sm], vec3(proj_coords.xy, compare_depth));
    } else if (method == 2) {
        // Poisson
        vec2 texel_size = 1.0 / vec2(textureSize(u_shadow_map[sm], 0));
        float radius = 2.5 * softness;
        float shadow = 0.0;
        for (int i = 0; i < POISSON_SAMPLES; ++i) {
            vec2 offset = poissonDisk[i] * texel_size * radius;
            shadow += texture(u_shadow_map[sm], vec3(proj_coords.xy + offset, compare_depth));
        }
        return shadow / float(POISSON_SAMPLES);
    } else {
        // PCF 5x5
        vec2 texel_size = 1.0 / vec2(textureSize(u_shadow_map[sm], 0));
        float shadow = 0.0;
        for (int x = -2; x <= 2; ++x) {
            for (int y = -2; y <= 2; ++y) {
                vec2 offset = vec2(float(x), float(y)) * texel_size * softness;
                shadow += texture(u_shadow_map[sm], vec3(proj_coords.xy + offset, compare_depth));
            }
        }
        return shadow / 25.0;
    }
}

/**
 * Compute hard shadow using hardware PCF (sampler2DShadow).
 * Single sample with automatic depth comparison + bilinear filtering.
 */
float compute_shadow(int light_index) {
    float bias = _get_shadow_bias();

    for (int sm = 0; sm < u_shadow_map_count; ++sm) {
        if (u_shadow_light_index[sm] != light_index) {
            continue;
        }

        vec4 light_space_pos = u_light_space_matrix[sm] * vec4(v_world_pos, 1.0);
        vec3 proj_coords = light_space_pos.xyz / light_space_pos.w;
        proj_coords = proj_coords * 0.5 + 0.5;

        if (proj_coords.x < 0.0 || proj_coords.x > 1.0 ||
            proj_coords.y < 0.0 || proj_coords.y > 1.0 ||
            proj_coords.z < 0.0 || proj_coords.z > 1.0) {
            return 1.0;
        }

        // Hardware PCF: texture() on sampler2DShadow does depth comparison
        return texture(u_shadow_map[sm], vec3(proj_coords.xy, proj_coords.z - bias));
    }

    return 1.0;
}

/**
 * Compute soft shadow with 5x5 PCF grid.
 * 25 samples using hardware depth comparison.
 * Softness controlled by shadow_softness setting.
 */
float compute_shadow_pcf(int light_index) {
    float bias = _get_shadow_bias();
    float softness = max(_get_shadow_softness_val(), 0.0);

    for (int sm = 0; sm < u_shadow_map_count; ++sm) {
        if (u_shadow_light_index[sm] != light_index) {
            continue;
        }

        vec4 light_space_pos = u_light_space_matrix[sm] * vec4(v_world_pos, 1.0);
        vec3 proj_coords = light_space_pos.xyz / light_space_pos.w;
        proj_coords = proj_coords * 0.5 + 0.5;

        if (proj_coords.x < 0.0 || proj_coords.x > 1.0 ||
            proj_coords.y < 0.0 || proj_coords.y > 1.0 ||
            proj_coords.z < 0.0 || proj_coords.z > 1.0) {
            return 1.0;
        }

        vec2 texel_size = 1.0 / vec2(textureSize(u_shadow_map[sm], 0));
        float compare_depth = proj_coords.z - bias;

        float shadow = 0.0;
        for (int x = -2; x <= 2; ++x) {
            for (int y = -2; y <= 2; ++y) {
                vec2 offset = vec2(float(x), float(y)) * texel_size * softness;
                shadow += texture(u_shadow_map[sm], vec3(proj_coords.xy + offset, compare_depth));
            }
        }

        return shadow / 25.0;
    }

    return 1.0;
}

/**
 * Compute high-quality soft shadow with Poisson disk sampling.
 * 16 samples with better distribution than grid, reduces banding artifacts.
 * Softness controlled by shadow_softness setting.
 */
float compute_shadow_poisson(int light_index) {
    float bias = _get_shadow_bias();
    float softness = max(_get_shadow_softness_val(), 0.0);

    for (int sm = 0; sm < u_shadow_map_count; ++sm) {
        if (u_shadow_light_index[sm] != light_index) {
            continue;
        }

        vec4 light_space_pos = u_light_space_matrix[sm] * vec4(v_world_pos, 1.0);
        vec3 proj_coords = light_space_pos.xyz / light_space_pos.w;
        proj_coords = proj_coords * 0.5 + 0.5;

        if (proj_coords.x < 0.0 || proj_coords.x > 1.0 ||
            proj_coords.y < 0.0 || proj_coords.y > 1.0 ||
            proj_coords.z < 0.0 || proj_coords.z > 1.0) {
            return 1.0;
        }

        vec2 texel_size = 1.0 / vec2(textureSize(u_shadow_map[sm], 0));
        float compare_depth = proj_coords.z - bias;
        float radius = 2.5 * softness;

        float shadow = 0.0;
        for (int i = 0; i < POISSON_SAMPLES; ++i) {
            vec2 offset = poissonDisk[i] * texel_size * radius;
            shadow += texture(u_shadow_map[sm], vec3(proj_coords.xy + offset, compare_depth));
        }

        return shadow / float(POISSON_SAMPLES);
    }

    return 1.0;
}

/**
 * Compute shadow using Cascaded Shadow Maps (CSM).
 * Selects appropriate cascade based on view-space depth.
 * Optionally blends between cascades for smooth transitions.
 */
float compute_shadow_cascaded(int light_index) {
    float bias = _get_shadow_bias();

    // Compute view-space depth (Y-forward convention: depth = view_pos.y)
    vec4 view_pos = u_view * vec4(v_world_pos, 1.0);
    float depth = view_pos.y;  // Y is forward in our convention

    int cascade_count = _get_cascade_count(light_index);
    bool do_blend = _get_cascade_blend(light_index) != 0;
    float blend_dist = _get_blend_distance(light_index);

    // Find cascade that contains this depth
    int cascade_sm = -1;
    int next_cascade_sm = -1;
    float blend_factor = 0.0;

    for (int sm = 0; sm < u_shadow_map_count; ++sm) {
        if (u_shadow_light_index[sm] != light_index) {
            continue;
        }

        float split_near = u_shadow_split_near[sm];
        float split_far = u_shadow_split_far[sm];

        if (depth >= split_near && depth < split_far) {
            cascade_sm = sm;

            // Check if in blend zone (near far edge)
            if (do_blend && (split_far - depth) < blend_dist) {
                int this_cascade_idx = u_shadow_cascade_index[sm];

                // Find next cascade
                for (int sm2 = 0; sm2 < u_shadow_map_count; ++sm2) {
                    if (u_shadow_light_index[sm2] != light_index) {
                        continue;
                    }
                    if (u_shadow_cascade_index[sm2] == this_cascade_idx + 1) {
                        next_cascade_sm = sm2;
                        blend_factor = 1.0 - (split_far - depth) / blend_dist;
                        break;
                    }
                }
            }
            break;
        }
    }

    // No cascade found - no shadow
    if (cascade_sm < 0) {
        return 1.0;
    }

    // Sample primary cascade
    float shadow1 = _sample_shadow_map(cascade_sm, v_world_pos, bias);

    // Blend with next cascade if needed
    if (next_cascade_sm >= 0 && blend_factor > 0.0) {
        float shadow2 = _sample_shadow_map(next_cascade_sm, v_world_pos, bias);
        return mix(shadow1, shadow2, blend_factor);
    }

    return shadow1;
}

/**
 * Compute shadow using method selected by shadow settings.
 * Automatically uses cascaded shadows if cascade_count > 1.
 * 0 = hard (single sample)
 * 1 = PCF 5x5 grid (default)
 * 2 = Poisson disk (16 samples)
 */
float compute_shadow_auto(int light_index) {
    // Check if this light uses cascades
    int cascade_count = _get_cascade_count(light_index);
    if (cascade_count > 1) {
        return compute_shadow_cascaded(light_index);
    }

    // Single cascade - use original methods
    int method = _get_shadow_method_val();
    if (method == 0) {
        return compute_shadow(light_index);
    } else if (method == 2) {
        return compute_shadow_poisson(light_index);
    } else {
        return compute_shadow_pcf(light_index);
    }
}

#endif // SHADOWS_GLSL
