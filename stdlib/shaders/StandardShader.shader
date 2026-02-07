@program StandardShader
@features lighting_ubo

// ============================================================
// Standard Shader - Blinn-Phong lighting with shadow support
// ============================================================
//
// A general-purpose shader with:
// - Diffuse (Lambert) + Specular (Blinn-Phong) lighting
// - Support for directional, point, and spot lights
// - Shadow mapping for directional lights
// - Albedo texture support
// - Scene ambient lighting
//
// Usage:
//   1. Deploy standard library to your project
//   2. Create material from this shader
//   3. Assign albedo texture and adjust color/shininess
//
// ============================================================

@phase opaque
@priority 0
@glDepthTest true
@glDepthMask true
@glCull true

@property Color u_color = Color(1.0, 1.0, 1.0, 1.0)
@property Float u_shininess = 32.0 range(1.0, 128.0)
@property Texture u_albedo_texture

@stage vertex
#version 330 core

layout(location = 0) in vec3 a_position;
layout(location = 1) in vec3 a_normal;
layout(location = 2) in vec2 a_uv;

uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_projection;

out vec3 v_world_pos;
out vec3 v_normal;
out vec2 v_uv;

void main() {
    vec4 world = u_model * vec4(a_position, 1.0);
    v_world_pos = world.xyz;
    v_normal = mat3(transpose(inverse(u_model))) * a_normal;
    v_uv = a_uv;
    gl_Position = u_projection * u_view * world;
}
@endstage

@stage fragment
#version 330 core

in vec3 v_world_pos;
in vec3 v_normal;
in vec2 v_uv;

#include "lighting.glsl"
#include "shadows.glsl"

// Material properties
uniform vec4 u_color;
uniform sampler2D u_albedo_texture;
uniform float u_shininess;

out vec4 FragColor;

void main() {
    vec3 N = normalize(v_normal);
    vec3 V = normalize(get_camera_position() - v_world_pos);

    // Sample albedo texture
    vec4 tex_color = texture(u_albedo_texture, v_uv);
    vec3 base_color = u_color.rgb * tex_color.rgb;

    // Start with ambient lighting
    vec3 result = base_color * get_ambient_color() * get_ambient_intensity();

    // Accumulate light contributions
    for (int i = 0; i < get_light_count(); ++i) {
        int type = get_light_type(i);
        vec3 radiance = get_light_color(i) * get_light_intensity(i);

        vec3 L;
        float dist;
        float weight = 1.0;

        if (type == LIGHT_TYPE_DIRECTIONAL) {
            L = normalize(-get_light_direction(i));
            dist = 1e9;
        } else {
            vec3 to_light = get_light_position(i) - v_world_pos;
            dist = length(to_light);
            L = dist > 0.0001 ? to_light / dist : vec3(0.0, 1.0, 0.0);

            weight *= compute_distance_attenuation(
                get_light_attenuation(i),
                get_light_range(i),
                dist
            );

            if (type == LIGHT_TYPE_SPOT) {
                weight *= compute_spot_weight(
                    get_light_direction(i),
                    L,
                    get_light_inner_angle(i),
                    get_light_outer_angle(i)
                );
            }
        }

        // Shadow for directional lights
        float shadow = 1.0;
        if (type == LIGHT_TYPE_DIRECTIONAL) {
            shadow = compute_shadow_auto(i);
        }

        // Diffuse (Lambert)
        float NdotL = max(dot(N, L), 0.0);
        vec3 diffuse = base_color * NdotL;

        // Specular (Blinn-Phong)
        float spec = blinn_phong_specular(N, L, V, u_shininess);
        vec3 specular = vec3(spec);

        // Combine with shadow
        result += (diffuse + specular) * radiance * weight * shadow;
    }

    FragColor = vec4(result, u_color.a * tex_color.a);
}
@endstage

@endphase

// ============================================================
// Shadow caster phase - renders to shadow map
// ============================================================

@phase shadow
@priority 0
@glDepthTest true
@glDepthMask true
@glCull true

@stage vertex
#version 330 core

layout(location = 0) in vec3 a_position;

uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_projection;

void main() {
    gl_Position = u_projection * u_view * u_model * vec4(a_position, 1.0);
}
@endstage

@stage fragment
#version 330 core

out vec4 FragColor;

void main() {
    // Depth is written automatically to depth buffer
    // Output depth to color for debugging/sampling
    float depth = gl_FragCoord.z;
    FragColor = vec4(depth, depth, depth, 1.0);
}
@endstage

@endphase
