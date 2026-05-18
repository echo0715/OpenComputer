package com.example;

public class App {
	private int counter = 0;

	public static void main(String[] args) {
		App a = new App();
		for (int i = 0; i < 5; i++) {
			a.counter++;
			System.out.println("tick " + a.counter);
		}
		System.out.println("done");
	}
}
