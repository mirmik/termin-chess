@program BlinnPhong
@features lighting_ubo

// ============================================================
// Blinn-Phong Shader - Canonical Implementation
// ============================================================
//
// Classic Blinn-Phong illumination model:
//   I = Ka*Ia + Kd*Id*(N·L) + Ks*Is*(N·H)^n
//
// Where:
//   Ka, Kd, Ks - material coefficients (ambient, diffuse, specular)
//   Ia, Id, Is - light intensities
//   N - surface normal
//   L - direction to light
//   H - half-vector: normalize(L + V)
//   V - direction to viewer
//   n - shininess exponent
//
// ============================================================

@phase opaque
@priority 0
@glDepthTest true
@glDepthMask true
@glCull true

@property Color u_diffuse_color = Color(1.0, 1.0, 1.0, 1.0)
@property Color u_specular_color = Color(1.0, 1.0, 1.0, 1.0)
@property Float u_ambient_factor = 1.0 range(0.0, 1.0)
@property Float u_shininess = 32.0 range(1.0, 256.0)
@property Texture2D u_diffuse_texture = "white"

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

    // Transform normal to world space (handles non-uniform scale)
    mat3 normal_matrix = transpose(inverse(mat3(u_model)));
    v_normal = normal_matrix * a_normal;

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
uniform vec4 u_diffuse_color;
uniform vec4 u_specular_color;
uniform sampler2D u_diffuse_texture;
uniform float u_ambient_factor;
uniform float u_shininess;

out vec4 FragColor;

void main() {
    // Normalize interpolated normal
    vec3 N = normalize(v_normal);

    // View direction
    vec3 V = normalize(get_camera_position() - v_world_pos);

    // Sample diffuse texture
    vec4 tex_color = texture(u_diffuse_texture, v_uv);
    vec3 Kd = u_diffuse_color.rgb * tex_color.rgb;  // Diffuse coefficient
    vec3 Ks = u_specular_color.rgb;                  // Specular coefficient
    float alpha = u_diffuse_color.a * tex_color.a;

    // Ambient term: Ka * Ia
    // Ka = Kd * ambient_factor (common approximation)
    vec3 Ka = Kd * u_ambient_factor;
    vec3 ambient = Ka * get_ambient_color() * get_ambient_intensity();

    // Accumulate light contributions
    vec3 diffuse_sum = vec3(0.0);
    vec3 specular_sum = vec3(0.0);

    for (int i = 0; i < get_light_count(); ++i) {
        vec3 L;           // Direction to light
        float atten = 1.0; // Attenuation

        // Compute light direction and attenuation based on light type
        if (get_light_type(i) == LIGHT_TYPE_DIRECTIONAL) {
            L = normalize(-get_light_direction(i));
        } else {
            vec3 to_light = get_light_position(i) - v_world_pos;
            float dist = length(to_light);
            L = to_light / max(dist, 0.0001);

            // Distance attenuation
            atten = compute_distance_attenuation(
                get_light_attenuation(i),
                get_light_range(i),
                dist
            );

            // Spot cone attenuation
            if (get_light_type(i) == LIGHT_TYPE_SPOT) {
                atten *= compute_spot_weight(
                    get_light_direction(i),
                    L,
                    get_light_inner_angle(i),
                    get_light_outer_angle(i)
                );
            }
        }

        // Shadow factor (directional lights only for now)
        float shadow = 1.0;
        if (get_light_type(i) == LIGHT_TYPE_DIRECTIONAL) {
            shadow = compute_shadow_auto(i);
        }

        // Light intensity
        vec3 Li = get_light_color(i) * get_light_intensity(i) * atten * shadow;

        // Diffuse term: Kd * (N·L)
        float NdotL = max(dot(N, L), 0.0);
        diffuse_sum += Kd * Li * NdotL;

        // Specular term: Ks * (N·H)^n
        // Only compute if surface faces the light
        if (NdotL > 0.0) {
            vec3 H = normalize(L + V);
            float NdotH = max(dot(N, H), 0.0);
            float spec = pow(NdotH, u_shininess);
            specular_sum += Ks * Li * spec;
        }
    }

    // Final color: Ambient + Diffuse + Specular
    vec3 color = ambient + diffuse_sum + specular_sum;

    FragColor = vec4(color, alpha);
}
@endstage

@endphase

// ============================================================
// Shadow caster phase
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
    FragColor = vec4(gl_FragCoord.z, 0.0, 0.0, 1.0);
}
@endstage

@endphase
