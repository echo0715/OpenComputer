package legacy;

public class LegacyService {
    public String greet(String name) {
        return "Hello, " + name;
    }

    public static void main(String[] args) {
        System.out.println(new LegacyService().greet("world"));
    }
}
