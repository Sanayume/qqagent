import axios from "axios"

export function getApiBaseUrl() {
  const configured = import.meta.env.VITE_API_URL || window.location.origin
  return configured.replace(/\/$/, "")
}

export function buildWsUrl(path: string, token?: string | null) {
  const wsBase = getApiBaseUrl().replace(/^http/, "ws") + "/"
  const url = new URL(path.replace(/^\//, ""), wsBase)
  if (token) {
    url.searchParams.set("token", token)
  }
  return url.toString()
}

const api = axios.create({
  baseURL: getApiBaseUrl(),
  timeout: 10000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token")
  if (token) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("token")
      window.location.href = "/login"
    }
    return Promise.reject(error)
  }
)

export default api
