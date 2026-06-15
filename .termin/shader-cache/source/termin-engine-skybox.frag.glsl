#version 450 core
layout(std140, binding = 1) uniform MaterialParams {
    mat4 u_view;
    mat4 u_projection;
    int u_skybox_type;
    vec4 u_skybox_color;
    vec4 u_skybox_top_color;
    vec4 u_skybox_bottom_color;
};

layout(location = 0) in vec3 v_dir;
layout(location = 0) out vec4 FragColor;


void main() {
    // 0 = gradient, 1 = solid - matches the TC_SKYBOX_* enum values in
    // core/tc_scene_skybox.h (TC_SKYBOX_GRADIENT=0, TC_SKYBOX_SOLID=1;
    // TC_SKYBOX_NONE is filtered out by the C++ caller before dispatch).
    if (u_skybox_type == 1) {
        FragColor = vec4(u_skybox_color.rgb, 1.0);
    } else {
        float t = normalize(v_dir).z * 0.5 + 0.5;
        vec3 c = mix(u_skybox_bottom_color.rgb, u_skybox_top_color.rgb, t);
        FragColor = vec4(c, 1.0);
    }
}
