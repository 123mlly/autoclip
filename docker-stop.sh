#!/bin/bash

# AutoClip Docker 停止脚本
# 版本: 1.0
# 功能: 停止AutoClip Docker服务

set -euo pipefail

# =============================================================================
# 配置区域
# =============================================================================

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# 图标定义
ICON_SUCCESS="✅"
ICON_ERROR="❌"
ICON_WARNING="⚠️"
ICON_INFO="ℹ️"
ICON_STOP="🛑"

# =============================================================================
# 工具函数
# =============================================================================

log_info() {
    echo -e "${BLUE}${ICON_INFO} $1${NC}"
}

log_success() {
    echo -e "${GREEN}${ICON_SUCCESS} $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}${ICON_WARNING} $1${NC}"
}

log_error() {
    echo -e "${RED}${ICON_ERROR} $1${NC}"
}

log_header() {
    echo -e "\n${PURPLE}${ICON_STOP} $1${NC}"
    echo -e "${PURPLE}$(printf '=%.0s' {1..50})${NC}"
}

# =============================================================================
# 停止函数
# =============================================================================

stop_services() {
    log_header "停止AutoClip服务"
    
    local mode="${1:-production}"
    
    log_info "停止服务 (模式: $mode)..."
    
    if [[ "$mode" == "dev" ]]; then
        if docker compose -f docker-compose.dev.yml down; then
            log_success "服务已停止"
        else
            log_error "停止服务失败"
            exit 1
        fi
    else
        # 生产：同时带上 gpu 叠加文件，确保 gpu 启动的 worker 一并拆除
        if docker compose -f docker-compose.yml -f docker-compose.gpu.yml down 2>/dev/null \
            || docker compose -f docker-compose.yml down; then
            log_success "服务已停止"
        else
            log_error "停止服务失败"
            exit 1
        fi
    fi
}

cleanup_containers() {
    log_header "清理容器"
    
    # 停止所有相关容器
    local containers=$(docker ps -a --filter "name=autoclip" --format "{{.Names}}" 2>/dev/null || true)
    
    if [[ -n "$containers" ]]; then
        log_info "发现以下AutoClip容器:"
        echo "$containers"
        
        if [[ "${1:-}" == "--force" ]]; then
            log_info "强制停止所有容器..."
            echo "$containers" | xargs docker stop 2>/dev/null || true
            echo "$containers" | xargs docker rm 2>/dev/null || true
            log_success "容器清理完成"
        else
            log_warning "使用 --force 参数强制清理容器"
        fi
    else
        log_success "没有发现AutoClip容器"
    fi
}

cleanup_images() {
    log_header "清理镜像"
    
    if [[ "${1:-}" == "--force" ]]; then
        log_info "清理未使用的镜像..."
        docker image prune -f
        log_success "镜像清理完成"
    else
        log_info "使用 --force 参数清理未使用的镜像"
    fi
}

cleanup_volumes() {
    log_header "清理数据卷"
    
    if [[ "${1:-}" == "--force" ]]; then
        log_warning "这将删除所有数据，包括项目文件和数据库！"
        read -p "确定要继续吗？(y/N): " -n 1 -r
        echo
        
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            log_info "清理数据卷..."
            docker volume prune -f
            log_success "数据卷清理完成"
        else
            log_info "取消清理数据卷"
        fi
    else
        log_info "使用 --force 参数清理未使用的数据卷"
    fi
}

show_status() {
    log_header "当前状态"
    
    echo -e "${BLUE}📊 容器状态:${NC}"
    docker compose ps 2>/dev/null || echo "  没有运行的服务"
    
    echo -e "\n${BLUE}🐳 AutoClip相关容器:${NC}"
    docker ps -a --filter "name=autoclip" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "  没有发现相关容器"
    
    echo -e "\n${BLUE}💾 数据卷:${NC}"
    docker volume ls --filter "name=autoclip" --format "table {{.Name}}\t{{.Driver}}\t{{.Size}}" 2>/dev/null || echo "  没有发现相关数据卷"
}

# =============================================================================
# 主函数
# =============================================================================

main() {
    local mode="production"
    local cleanup=false
    local force=false
    
    # 解析参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            "dev")
                mode="development"
                shift
                ;;
            "--cleanup")
                cleanup=true
                shift
                ;;
            "--force")
                force=true
                shift
                ;;
            "help"|"-h"|"--help")
                show_help
                exit 0
                ;;
            *)
                log_error "未知参数: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    log_header "AutoClip Docker 停止器 v1.0"
    
    # 停止服务
    stop_services "$mode"
    
    # 清理（如果需要）
    if [[ "$cleanup" == true ]]; then
        cleanup_containers "$force"
        cleanup_images "$force"
        cleanup_volumes "$force"
    fi
    
    # 显示状态
    show_status
    
    echo -e "\n${GREEN}🎉 AutoClip Docker 服务已停止${NC}"
}

# 显示帮助信息
show_help() {
    echo "AutoClip Docker 停止脚本"
    echo ""
    echo "用法:"
    echo "  $0 [选项]"
    echo ""
    echo "选项:"
    echo "  dev          停止开发环境"
    echo "  --cleanup    停止后清理资源"
    echo "  --force      强制清理（包括数据）"
    echo "  help         显示帮助信息"
    echo ""
    echo "示例:"
    echo "  $0                    # 停止生产环境"
    echo "  $0 dev                # 停止开发环境"
    echo "  $0 --cleanup          # 停止并清理资源"
    echo "  $0 --cleanup --force  # 停止并强制清理所有资源"
    echo "  $0 help               # 显示帮助"
    echo ""
    echo "注意:"
    echo "  --force 参数会删除所有数据，请谨慎使用！"
}

# 运行主函数
main "$@"
